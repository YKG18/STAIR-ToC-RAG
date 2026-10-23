# STAIR-ToC-RAG

**Structure-Aware Table-of-Contents Retrieval-Augmented Generation**

STAIR-ToC-RAG is a RAG system that understands the hierarchical structure of your documents. Instead of blindly chunking text, it extracts the Table of Contents (chapters → sections → paragraphs) from PDFs and preserves that structure throughout the entire retrieval pipeline — so every answer comes with its exact location in the source document.

## How It Works

1. **Parse** — Upload a PDF and the parser extracts its structure using embedded bookmarks or, when those aren't available, font-size heuristics to detect chapter and section headings.
2. **Index** — Each paragraph is turned into an addressed chunk (`Chapter > Section > Paragraph N`), and that address is embedded alongside the content, giving the retriever positional/structural signal.
3. **Retrieve** — Queries are matched by cosine similarity against the chunk embeddings. A *parent-context expansion* step automatically pulls in the preceding and following paragraphs within the same section, so results never lose the context they depend on.
4. **Generate** — Retrieved context is sent to a local Ollama LLM to produce a grounded answer, explanation, or quiz.

## Project Structure

```
├── src/
│   ├── parser/            # PDF → Chapter > Section > Paragraph tree
│   ├── indexer/           # Chunking, embedding (sentence-transformers), vector storage
│   ├── retriever/         # STAIR retriever with parent-context expansion
│   └── api/               # FastAPI server (/ingest, /query, /health)
├── app/
│   ├── dashboard.py       # Streamlit web UI
│   ├── desktop_ui.py      # CustomTkinter desktop chatbot (Ask / Explain / Quiz modes)
│   └── rag_client.py      # Client logic: retrieve from RAG → generate with Ollama
├── scripts/
│   └── check_setup.py     # Pre-flight checks (Python version, packages, server, Ollama)
├── data/
│   ├── raw/               # Place source PDFs here
│   └── processed/         # Index cache lives here
├── launcher.py            # One-click setup: venv, deps, Ollama, server, desktop UI
├── START.bat              # Windows double-click launcher
├── docker-compose.yml     # Full stack: Qdrant + API + Streamlit dashboard
├── requirements.txt       # All Python dependencies
├── requirements-run.txt   # Minimal deps for the launcher/venv
└── requirements-desktop.txt  # Extra deps for the desktop chatbot
```

## Prerequisites

- **Python 3.9+**
- **Ollama** — [Download here](https://ollama.com/download)
- **Docker** *(optional, for the Qdrant-backed production setup)*

## How to Run

### Option 1 — One-Click (Windows)

Double-click **`START.bat`**. It will:
- Install Python via `winget` if missing
- Create a virtual environment and install dependencies
- Install Ollama and pull the `gemma3:4b-it-qat` model if needed
- Start the RAG API server
- Launch the desktop chatbot UI

That's it — no manual steps required on the first or any subsequent run.

### Option 2 — Manual Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-desktop.txt

# 3. Start Ollama and pull the model
ollama serve
ollama pull gemma3:4b-it-qat

# 4. Start the RAG API server
uvicorn src.api.main:app --port 8000

# 5. Launch the Desktop Chatbot
python -m app.desktop_ui
```

Or launch the **Streamlit dashboard** instead:

```bash
streamlit run app/dashboard.py
```

### Option 3 — Docker Compose (Qdrant + API + Dashboard)

```bash
# 1. Copy and configure environment variables
cp .env.example .env

# 2. Start the full stack
docker compose up --build
```

This starts:

| Service       | URL                      |
|---------------|--------------------------|
| Qdrant        | `http://localhost:6333`   |
| RAG API       | `http://localhost:8000`   |
| Streamlit UI  | `http://localhost:8501`   |

> **Note:** The Docker setup runs the Streamlit dashboard. The desktop chatbot (`desktop_ui.py`) requires a display and should be run outside Docker.

## Environment Variables

| Variable          | Default                    | Description                              |
|-------------------|----------------------------|------------------------------------------|
| `VECTOR_DB_URL`   | `http://localhost:6333`    | Qdrant server URL                        |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2`        | Sentence-transformers model for embeddings |
| `API_HOST`        | `0.0.0.0`                 | Host the API binds to                    |
| `API_PORT`        | `8000`                    | Port the API listens on                  |

## License

This project is licensed under the [MIT License](LICENSE).
