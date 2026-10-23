import re
import time

import requests

RAG_URL = "http://localhost:8000/query"
INGEST_URL = "http://localhost:8000/ingest"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma3:4b-it-qat"

# Short, simple prompts, one per mode
PROMPTS = {
    "ask": (
        "Answer the question using only the context. "
        "Be brief. If the context lacks the answer, say so."
        "If you have knowledge about the topic then answer it"
    ),
    "explain": (
        "Explain the topic in depth using only the context. "
        "Give a simple overview, then key concepts, then details. "
        "Only include an example if the context contains one; never invent examples or facts. "
        "Ignore context that is not about the topic itself."
        "If you have knowledge about the topic then explain it"
    ),
    "quiz": (
        "Write 5 multiple-choice questions that test understanding of the topic's concepts, "
        "definitions and how things work, using only the context. "
        "Never ask about the book, its chapters, its structure, or exercises. "
        "Skip context that is just an introduction, summary or table of contents. "
        "Give 4 options (A-D) each, exactly one correct. Put the answer key at the end."
    ),
}
TOP_K = {"ask": 5, "explain": 8, "quiz": 8}
_FILLER = re.compile(
    r"^\s*(please\s+)?(test me on|quiz me on|quiz me about|quiz on|test me about|"
    r"explain|tell me about|what is|what are)\s+",
    re.I,
)

# Only used by "ask" mode, to resolve follow-up questions
history = []


def extract_context(data):
    if isinstance(data, str):
        return data

    if isinstance(data, list):
        chunks = data
    elif isinstance(data, dict):
        for key in ("context", "chunks", "documents", "results", "data"):
            if key in data:
                value = data[key]

                if isinstance(value, str):
                    return value

                if isinstance(value, list):
                    chunks = value
                    break
        else:
            chunks = [data]
    else:
        raise ValueError(f"Unexpected RAG response: {type(data)}")

    texts = []

    for chunk in chunks:
        if isinstance(chunk, str):
            texts.append(chunk)
        elif isinstance(chunk, dict):
            text = (
                chunk.get("text")
                or chunk.get("content")
                or chunk.get("page_content")
                or chunk.get("document")
            )

            if isinstance(text, str):
                texts.append(text)
            else:
                texts.append(str(chunk))
        else:
            texts.append(str(chunk))

    return "\n\n".join(texts)


def _log(msg):
    print(f"[app] {msg}", flush=True)


def run(mode: str, text: str) -> str:
    """mode: 'ask' | 'explain' | 'quiz'. text: question or topic."""
    use_history = mode == "ask"
    recent_history = history[-10:] if use_history else []

    topic = _FILLER.sub("", text).strip() or text
    rag_query = text if mode == "ask" else topic
    if recent_history:
        conversation = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
            for m in recent_history
        )
        rag_query = (
            f"Conversation so far:\n{conversation}\n\n"
            f"Current question: {text}\n\n"
            "Retrieve documents relevant to the current question "
            "in the context of this conversation."
        )

    t0 = time.time()
    _log(f"{mode.upper()} request: {text!r}")
    # 1. Retrieve
    _log(f"Retrieving top_k={TOP_K[mode]} for query {rag_query[:80]!r}")
    r = requests.post(RAG_URL, json={"query": rag_query, "top_k": TOP_K[mode]}, timeout=60)
    r.raise_for_status()
    context = extract_context(r.json())
    if not context.strip():
        context = "No relevant documents were retrieved."

    _log(f"Retrieved {len(context)} chars in {time.time()-t0:.1f}s. Sending to Ollama ({MODEL})...")
    # 2. Generate
    label = "Question" if mode == "ask" else "Topic"
    messages = [
        {"role": "system", "content": PROMPTS[mode]},
        *recent_history,
        {
            "role": "user",
            "content": f"Context:\n{context}\n\n{label}: {text if mode == 'ask' else topic}",
        },
    ]
    o = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "stream": False, "messages": messages,
              "options": {"temperature": 0.2, "num_ctx": 8192}},
        timeout=300,
    )
    o.raise_for_status()
    answer = o.json()["message"]["content"]
    _log(f"Ollama answered ({len(answer)} chars). Total {time.time()-t0:.1f}s")

    if use_history:
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
    return answer


def ingest_pdf(path: str) -> str:
    """Upload a PDF to the RAG server. Returns a short status message."""
    _log(f"Uploading {path} to server (server terminal shows parse/embed progress)...")
    with open(path, "rb") as f:
        r = requests.post(
            INGEST_URL,
            files={"file": (path.replace("\\", "/").split("/")[-1], f, "application/pdf")},
            timeout=600,
        )
    r.raise_for_status()
    try:
        return str(r.json())
    except ValueError:
        return r.text or "Uploaded."
