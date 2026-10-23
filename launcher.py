"""One-click setup + run. Asks once (only on first run), then does everything itself."""
import json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)
MODEL = "gemma3:4b-it-qat"
VENV = ROOT / ".venv"
PY = VENV / "Scripts" / "python.exe"
MARK = VENV / ".deps_ok"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


def find_ollama():
    p = shutil.which("ollama")
    if p:
        return p
    c = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(c) if c.exists() else None


def install_ollama():
    print("Installing Ollama...")
    if shutil.which("winget"):
        subprocess.run(["winget", "install", "-e", "--id", "Ollama.Ollama", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements"])
    if not find_ollama():
        exe = ROOT / "OllamaSetup.exe"
        urllib.request.urlretrieve("https://ollama.com/download/OllamaSetup.exe", exe)
        subprocess.run([str(exe), "/VERYSILENT", "/NORESTART"])
        exe.unlink(missing_ok=True)
    return find_ollama()


def main():
    oll = find_ollama()
    need_deps = not MARK.exists()
    have_model = False
    if oll:
        r = subprocess.run([oll, "list"], capture_output=True, text=True, creationflags=NOWIN)
        have_model = MODEL.split(":")[0] in r.stdout and MODEL.split(":")[1] in r.stdout
    todo = []
    if need_deps: todo.append("Python packages (~1-2 GB incl. embedding libs)")
    if not oll: todo.append("Ollama")
    if not have_model: todo.append(f"model {MODEL} (~4 GB)")
    if todo:
        print("First-time setup will install:\n  - " + "\n  - ".join(todo))
        if input("Proceed? Everything else is automatic. [Y/n]: ").strip().lower() == "n":
            return
    if not PY.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])
    if need_deps:
        subprocess.check_call([str(PY), "-m", "pip", "install", "-q", "--upgrade", "pip"])
        subprocess.check_call([str(PY), "-m", "pip", "install", "-r", "requirements-run.txt"])
        MARK.write_text("ok")
    if not oll:
        oll = install_ollama()
        if not oll:
            sys.exit("Ollama install failed. Install from https://ollama.com/download and rerun.")
    if not up("http://localhost:11434"):
        subprocess.Popen([oll, "serve"], creationflags=NOWIN)
        for _ in range(60):
            if up("http://localhost:11434"): break
            time.sleep(1)
    if not have_model:
        subprocess.check_call([oll, "pull", MODEL])

    server = None
    if not up("http://localhost:8000/health"):
        server = subprocess.Popen([str(PY), "-m", "uvicorn", "src.api.main:app", "--port", "8000", "--log-level", "info"],
                                  env={**os.environ, "PYTHONUNBUFFERED": "1"})
        print("Starting RAG server (first run downloads the embedding model, may take a few minutes)...")
        for _ in range(900):
            if up("http://localhost:8000/health"): break
            if server.poll() is not None:
                sys.exit("RAG server failed to start.")
            time.sleep(1)
    print("Launching app...")
    try:
        subprocess.run([str(PY), "-m", "app.desktop_ui"], env={**os.environ, "PYTHONUNBUFFERED": "1"})
    finally:
        if server:
            server.terminate()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Error:", e)
        input("Press Enter to close...")
