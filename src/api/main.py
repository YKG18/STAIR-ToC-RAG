"""FastAPI service exposing document ingestion and ToC-aware query endpoints."""
from __future__ import annotations

import hashlib
import json
import pickle
import shutil
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.indexer.pipeline import HierarchicalIndexer
from src.indexer.vector_store import InMemoryVectorStore, default_embedder
from src.parser.base import BaseParser
from src.parser.pdf_heuristics import PDFHeuristicParser
from src.retriever.stair_retriever import STAIRRetriever

app = FastAPI(
    title="STAIR-ToC-RAG API",
    description="Structure-aware, table-of-contents-native retrieval.",
    version="0.1.0",
)

# Single shared embedder + store for this process.
# Swap InMemoryVectorStore for QdrantVectorStore in production
# (see src/indexer/vector_store.py) — the rest of the code is unaffected.
_embed_fn = default_embedder()
_vector_store = InMemoryVectorStore()
_indexer = HierarchicalIndexer(vector_store=_vector_store, embed_fn=_embed_fn)
_retriever = STAIRRetriever(vector_store=_vector_store, embed_fn=_embed_fn)

# ---- Disk cache: index survives restarts; same PDF is never re-embedded ----
_CACHE = Path("data/processed/index_cache.pkl")
_docs: Dict[str, dict] = {}  # sha256 -> {"filename", "chunks"}


def _load_cache() -> None:
    if not _CACHE.exists():
        return
    try:
        with open(_CACHE, "rb") as f:
            state = pickle.load(f)
        _vector_store._chunks = state["chunks"]
        _vector_store._vectors = state["vectors"]
        _docs.update(state["docs"])
        print(f"[cache] Loaded {len(state['chunks'])} chunks from {_CACHE} "
              f"({', '.join(d['filename'] for d in _docs.values())})", flush=True)
    except Exception as e:
        print(f"[cache] Ignoring unreadable cache ({e}); starting empty", flush=True)


def _save_cache() -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump({"chunks": _vector_store._chunks, "vectors": _vector_store._vectors,
                     "docs": _docs}, f)
    tmp.replace(_CACHE)
    print(f"[cache] Saved index to {_CACHE}", flush=True)


_load_cache()

_PARSERS: Dict[str, BaseParser] = {".pdf": PDFHeuristicParser()}


class QueryRequest(BaseModel):
    query: str
    top_k: int = 3


class QueryResult(BaseModel):
    toc_address: str
    content: str
    score: float
    context_before: Optional[str] = None
    context_after: Optional[str] = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "indexed_chunks": len(_vector_store.all_chunks()),
            "documents": [d["filename"] for d in _docs.values()]}


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    parser = _PARSERS.get(suffix)
    if parser is None:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    digest = hashlib.sha256(Path(tmp_path).read_bytes()).hexdigest()
    if digest in _docs:
        Path(tmp_path).unlink(missing_ok=True)
        print(f"[ingest] {file.filename} already indexed - using cache (skipped)", flush=True)
        return {"filename": file.filename, "chunks_indexed": _docs[digest]["chunks"], "cached": True}

    t0 = time.time()
    print(f"[ingest] Received {file.filename}. Parsing PDF structure...", flush=True)
    try:
        tree = parser.parse(tmp_path)
        doc_dict = BaseParser.tree_to_dict(tree)
        print(f"[ingest] Parsed in {time.time()-t0:.1f}s. Chunking + embedding (progress bar below)...", flush=True)
        chunks = _indexer.index_document(doc_dict)
        print(f"[ingest] Done: {len(chunks)} chunks indexed in {time.time()-t0:.1f}s", flush=True)
        _docs[digest] = {"filename": file.filename, "chunks": len(chunks)}
        _save_cache()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"filename": file.filename, "chunks_indexed": len(chunks)}


@app.post("/query", response_model=List[QueryResult])
def query(request: QueryRequest) -> List[QueryResult]:
    if len(_vector_store.all_chunks()) == 0:
        raise HTTPException(status_code=400, detail="Index is empty. Call /ingest first.")
    print(f"[query] '{request.query[:80]}' top_k={request.top_k}", flush=True)
    results = _retriever.retrieve(request.query, top_k=request.top_k)
    for r in results:
        d = r.as_dict()
        print(f"[query]   {d['score']:.3f}  {d['toc_address']}", flush=True)
    return [QueryResult(**r.as_dict()) for r in results]
