"""Prerequisites checker/installer plus uvicorn (RAG server) and Ollama tests.

Run:  python scripts/check_setup.py          (asks before installing)
      python scripts/check_setup.py --yes    (installs without asking)
"""
import importlib
import shutil
import subprocess
import sys

import requests

RAG_BASE = "http://localhost:8000"
OLLAMA_BASE = "http://localhost:11434"
MODEL = "gemma3:4b-it-qat"

# import name -> pip name
PIP_PACKAGES = {
    "requests": "requests",
    "customtkinter": "customtkinter",
    "uvicorn": "uvicorn",
}

AUTO_YES = "--yes" in sys.argv


def ok(msg):
    print(f"  [OK]   {msg}")


def fail(msg):
    print(f"  [FAIL] {msg}")


def confirm(question):
    if AUTO_YES:
        return True
    return input(f"  {question} [y/N]: ").strip().lower() == "y"


def check_python():
    print("Python")
    if sys.version_info >= (3, 9):
        ok(f"Python {sys.version.split()[0]}")
        return True
    fail(f"Python {sys.version.split()[0]} found, need 3.9+")
    return False


def check_packages():
    print("Python packages")
    all_ok = True
    for module, pip_name in PIP_PACKAGES.items():
        try:
            importlib.import_module(module)
            ok(pip_name)
        except ImportError:
            fail(f"{pip_name} is missing")
            if confirm(f"Install {pip_name}?"):
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pip_name]
                )
                if result.returncode == 0:
                    ok(f"{pip_name} installed")
                    continue
            all_ok = False

    try:
        import tkinter  # noqa: F401
        ok("tkinter")
    except ImportError:
        fail("tkinter is missing (Linux: sudo apt install python3-tk)")
        all_ok = False
    return all_ok


def test_uvicorn():
    print("RAG server (uvicorn)")
    try:
        import uvicorn
        ok(f"uvicorn {getattr(uvicorn, '__version__', '')}".strip())
    except ImportError:
        fail("uvicorn not installed")
        return False

    try:
        requests.get(RAG_BASE, timeout=5)
        ok(f"server reachable at {RAG_BASE}")
    except requests.RequestException:
        fail(f"nothing listening at {RAG_BASE}")
        print("         Start it, e.g.: uvicorn src.api.main:app --port 8000")
        return False

    # Optional: confirm the routes we need exist (FastAPI exposes openapi.json)
    try:
        paths = requests.get(f"{RAG_BASE}/openapi.json", timeout=5).json()["paths"]
        for route in ("/query", "/ingest"):
            (ok if route in paths else fail)(
                f"route {route} " + ("found" if route in paths else "NOT found")
            )
    except (requests.RequestException, KeyError, ValueError):
        print("  [..]   could not read /openapi.json (skipping route check)")

    try:
        r = requests.post(f"{RAG_BASE}/query", json={"query": "test"}, timeout=60)
        (ok if r.ok else fail)(f"/query test returned HTTP {r.status_code}")
        return r.ok
    except requests.RequestException as e:
        fail(f"/query test failed: {e}")
        return False


def test_ollama():
    print("Ollama")
    if shutil.which("ollama"):
        ok("ollama is installed")
    else:
        fail("ollama not found. Install from https://ollama.com/download")
        return False

    try:
        tags = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5).json()
        ok(f"server running at {OLLAMA_BASE}")
    except requests.RequestException:
        fail("server not running. Start it with: ollama serve")
        return False

    names = [m.get("name", "") for m in tags.get("models", [])]
    if MODEL in names:
        ok(f"model {MODEL} is available")
    else:
        fail(f"model {MODEL} not pulled")
        if confirm(f"Run 'ollama pull {MODEL}'?"):
            if subprocess.run(["ollama", "pull", MODEL]).returncode != 0:
                return False
            ok("model pulled")
        else:
            return False

    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model": MODEL,
                "stream": False,
                "messages": [{"role": "user", "content": "Reply with: ok"}],
            },
            timeout=180,
        )
        r.raise_for_status()
        ok("test chat works: " + r.json()["message"]["content"].strip()[:40])
        return True
    except (requests.RequestException, KeyError) as e:
        fail(f"test chat failed: {e}")
        return False


def run_all():
    results = [check_python(), check_packages(), test_uvicorn(), test_ollama()]
    print()
    if all(results):
        print("All checks passed. Run: python -m app.desktop_ui")
    else:
        print("Some checks failed. Fix the items above and re-run.")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)
