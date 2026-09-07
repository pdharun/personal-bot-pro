import asyncio
import logging
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

logging.disable(logging.INFO)

from main import PersonalBot

BOT_COLOR = "#0f1923"
ACCENT = "#00e5ff"
TEXT_COLOR = "#e8e8e8"
CARD = "#16232e"

COMMANDS = {
    "Binance": [
        ("BTC live price", "check binance BTCUSDT"),
        ("ETH live price", "check binance ETHUSDT"),
        ("BTC trend", "analyze trend BTCUSDT"),
    ],
    "DSE": [
        ("Market overview", "dse"),
        ("BRACBANK", "dse BRACBANK"),
    ],
    "Facebook Ads": [
        ("List campaigns", "list campaigns"),
        ("Ads insights (7d)", "insights"),
    ],
    "Trading": [
        ("Trader status", "trader status"),
        ("BTC SMA trade (paper)", "trade run BTCUSDT sma_cross"),
        ("Alert BTC 90k", "alert BTCUSDT above 90000"),
        ("List alerts", "alert list"),
    ],
    "System": [
        ("Help", "help"),
        ("Clear", "__clear__"),
    ],
}


class BotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Personal Bot v1.0")
        self.root.geometry("860x640")
        self.root.configure(bg=BOT_COLOR)
        self.root.minsize(700, 500)

        self.bot = None
        self.loop = None
        self.bot_thread = None
        self._history = []

        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self.root, bg=BOT_COLOR)
        header.pack(fill="x", padx=16, pady=(14, 6))

        title = tk.Label(
            header, text="MY PERSONAL AI BOT",
            font=("Segoe UI", 16, "bold"), fg=ACCENT, bg=BOT_COLOR,
        )
        title.pack(side="left")

        status = tk.Label(
            header, text="", font=("Segoe UI", 9),
            fg="#7ee787", bg=BOT_COLOR,
        )
        status.pack(side="right")

        body = tk.Frame(self.root, bg=BOT_COLOR)
        body.pack(fill="both", expand=True, padx=16, pady=6)

        self.output = scrolledtext.ScrolledText(
            body, wrap="word", font=("Consolas", 10),
            bg=CARD, fg=TEXT_COLOR, insertbackground=ACCENT,
            relief="flat", borderwidth=0, padx=12, pady=12,
        )
        self.output.pack(fill="both", expand=True)
        self.output.configure(state="disabled")

        input_row = tk.Frame(self.root, bg=BOT_COLOR)
        input_row.pack(fill="x", padx=16, pady=(8, 10))

        self.entry = tk.Entry(
            input_row, font=("Consolas", 11),
            bg=CARD, fg=TEXT_COLOR, insertbackground=ACCENT,
            relief="flat",
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry.bind("<Return>", lambda e: self._send_command())
        self.entry.focus_set()

        send_btn = tk.Button(
            input_row, text="Send", command=self._send_command,
            bg=ACCENT, fg=BOT_COLOR, font=("Segoe UI", 10, "bold"),
            relief="flat", padx=18, pady=8, cursor="hand2",
        )
        send_btn.pack(side="left", padx=(8, 0))

        self._build_quick_buttons()

        self._append("Personal Bot v1.0\nType a command or click a button below.\n", accent=True)
        self._append("Tip: type 'help' to see all commands\n", accent=False)
        self._start_bot()

    def _build_quick_buttons(self):
        bar = tk.Frame(self.root, bg=BOT_COLOR)
        bar.pack(fill="x", padx=16, pady=(0, 12))

        for group, items in COMMANDS.items():
            group_frame = tk.LabelFrame(
                bar, text=group, fg=ACCENT, bg=BOT_COLOR,
                font=("Segoe UI", 8, "bold"), bd=0,
            )
            group_frame.pack(side="left", padx=(0, 14), fill="y")
            for label, cmd in items:
                btn = tk.Button(
                    group_frame, text=label, command=lambda c=cmd: self._quick(c),
                    bg=CARD, fg=TEXT_COLOR, font=("Segoe UI", 8),
                    relief="flat", padx=8, pady=3, cursor="hand2",
                    activebackground=ACCENT, activeforeground=BOT_COLOR,
                )
                btn.pack(fill="x", pady=2)

    def _start_bot(self):
        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.bot = PersonalBot()
            self.loop.run_until_complete(self.bot.start())
            self.loop.run_forever()

        self.bot_thread = threading.Thread(target=run, daemon=True)
        self.bot_thread.start()

    def _append(self, text, accent=False):
        self.output.configure(state="normal")
        tag = "accent" if accent else "normal"
        self.output.tag_config(tag)
        if accent:
            self.output.insert("end", text, "accent")
        else:
            self.output.insert("end", text, "normal")
        self.output.insert("end", "\n", "normal")
        self.output.configure(state="disabled")
        self.output.see("end")

    def _quick(self, cmd):
        if cmd == "__clear__":
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.configure(state="disabled")
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, cmd)
        self._send_command()

    def _send_command(self):
        cmd = self.entry.get().strip()
        if not cmd:
            return
        self.entry.delete(0, "end")
        if cmd == "__clear__":
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.configure(state="disabled")
            return
        self._append(f">> {cmd}", accent=True)
        self._run_async_command(cmd)

    def _run_async_command(self, cmd):
        def worker():
            try:
                if self.loop and self.bot:
                    result = asyncio.run_coroutine_threadsafe(
                        self.bot.process_command(cmd), self.loop
                    ).result(timeout=60)
                else:
                    result = "Bot not ready"
            except Exception as e:
                result = f"Error: {e}"
            self.root.after(0, self._append, str(result))

        threading.Thread(target=worker, daemon=True).start()

    def on_close(self):
        if self.loop and self.bot:
            try:
                self.loop.call_soon_threadsafe(
                    self.loop.create_task, self.bot.stop()
                )
            except Exception:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = BotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()