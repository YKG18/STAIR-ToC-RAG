import re
import threading
from tkinter import filedialog

import customtkinter as ctk
import requests

from app import rag_client as chatbot

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

HINTS = {
    "Ask": "Type a question...",
    "Explain": "Type a topic to explain in depth...",
    "Quiz": "Type a topic to be quizzed on...",
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RAG Chatbot")
        self.geometry("820x640")
        self.minsize(560, 480)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top bar: mode selector + upload + clear
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        top.grid_columnconfigure(0, weight=1)

        self.mode = ctk.CTkSegmentedButton(
            top, values=["Ask", "Explain", "Quiz"], command=self.on_mode
        )
        self.mode.set("Ask")
        self.mode.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(top, text="Upload PDF", width=110, command=self.upload).grid(
            row=0, column=1, padx=(8, 0)
        )
        ctk.CTkButton(
            top, text="Clear", width=70, fg_color="gray30", hover_color="gray40",
            command=self.clear,
        ).grid(row=0, column=2, padx=(8, 0))

        # Chat area
        self.chat = ctk.CTkTextbox(self, wrap="word", font=("Segoe UI", 14))
        self.chat.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)
        self.chat.tag_config("you", foreground="#5aa9ff")
        self.chat.tag_config("bot", foreground="#e6e6e6")
        self.chat.tag_config("sys", foreground="#9aa0a6")
        tb = self.chat._textbox
        tb.tag_config("b", font=("Segoe UI", 14, "bold"))
        tb.tag_config("i", font=("Segoe UI", 14, "italic"))
        tb.tag_config("h", font=("Segoe UI", 16, "bold"), foreground="#ffffff")
        tb.tag_config("code", font=("Consolas", 13), foreground="#ffb86c", background="#2b2b2b")
        self.chat.configure(state="disabled")

        # Input row
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 8))
        bottom.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(bottom, placeholder_text=HINTS["Ask"], height=40)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda e: self.send())

        self.send_btn = ctk.CTkButton(bottom, text="Send", width=90, height=40,
                                      command=self.send)
        self.send_btn.grid(row=0, column=1, padx=(8, 0))

        self.status = ctk.CTkLabel(self, text="Ready", anchor="w", text_color="gray60")
        self.status.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10))

        self.log("Upload a PDF, pick a mode, and start.\n", "sys")

        def health():
            h = requests.get("http://localhost:8000/health", timeout=5).json()
            return h if h.get("indexed_chunks") else None

        def loaded(h, err):
            if h:
                self.log(f"Loaded saved index: {', '.join(h['documents'])} "
                         f"({h['indexed_chunks']} chunks). No upload needed.\n", "sys")

        self.run_in_thread(health, loaded)

    # ---- helpers ----
    def log(self, text, tag="bot"):
        self.chat.configure(state="normal")
        self.chat.insert("end", text + "\n", tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def log_md(self, text):
        """Render basic markdown (headers, bullets, **bold**, *italic*, `code`, ``` blocks)."""
        tb = self.chat._textbox
        self.chat.configure(state="normal")
        in_code = False
        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                tb.insert("end", "    " + line + "\n", ("code",))
                continue
            base = ("bot",)
            m = re.match(r"^(\s*)(#{1,6})\s+(.*)", line)
            if m:
                tb.insert("end", m.group(3) + "\n", ("h",))
                continue
            m = re.match(r"^(\s*)[*\-+]\s+(.*)", line)
            if m:
                line = m.group(1) + "\u2022 " + m.group(2)
            if re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", line):
                tb.insert("end", "\u2500" * 30 + "\n", base)
                continue
            for part in re.split(r"(\*\*.+?\*\*|`[^`]+`|\*[^*\s][^*]*?\*)", line):
                if part.startswith("**") and part.endswith("**") and len(part) > 4:
                    tb.insert("end", part[2:-2], ("b",))
                elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                    tb.insert("end", part[1:-1], ("code",))
                elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                    tb.insert("end", part[1:-1], ("i",))
                else:
                    tb.insert("end", part, base)
            tb.insert("end", "\n")
        tb.insert("end", "\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def set_busy(self, busy, msg="Ready"):
        self.send_btn.configure(state="disabled" if busy else "normal")
        self.status.configure(text=msg)

    def on_mode(self, value):
        self.entry.configure(placeholder_text=HINTS[value])

    def clear(self):
        chatbot.history.clear()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.log("Conversation cleared.\n", "sys")

    def run_in_thread(self, work, on_done):
        def target():
            try:
                result, err = work(), None
            except requests.RequestException as e:
                result, err = None, f"API error: {e}"
            except Exception as e:
                result, err = None, f"Error: {e}"
            self.after(0, lambda: on_done(result, err))

        threading.Thread(target=target, daemon=True).start()

    # ---- actions ----
    def send(self):
        text = self.entry.get().strip()
        if not text or self.send_btn.cget("state") == "disabled":
            return
        mode = self.mode.get()
        self.entry.delete(0, "end")
        self.log(f"You ({mode}): {text}", "you")
        self.set_busy(True, "Thinking...")

        def done(answer, err):
            if err:
                self.log(f"\n{err}\n", "sys")
            else:
                self.log_md("\n" + answer)
            self.set_busy(False)

        self.run_in_thread(lambda: chatbot.run(mode.lower(), text), done)

    def upload(self):
        path = filedialog.askopenfilename(
            title="Choose a PDF", filetypes=[("PDF files", "*.pdf")]
        )
        if not path:
            return
        name = path.replace("\\", "/").split("/")[-1]
        self.log(f"Uploading {name}...", "sys")
        self.set_busy(True, "Uploading PDF...")

        def done(result, err):
            self.log(f"{err or 'Ingested: ' + str(result)}\n", "sys")
            self.set_busy(False)

        self.run_in_thread(lambda: chatbot.ingest_pdf(path), done)


if __name__ == "__main__":
    App().mainloop()
