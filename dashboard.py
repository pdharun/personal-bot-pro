"""Personal Bot Pro Dashboard v3 - TradingView style."""
import asyncio
import datetime
import logging
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

logging.disable(logging.INFO)

import matplotlib
matplotlib.use("TkAgg")

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from main import PersonalBot
from tools.market_data import provider, COIN_NAMES
from tools.indicators import all_indicators, signal_summary

DEFAULT_SYMBOLS = list(COIN_NAMES.keys())[:40]

# ---------------- THEME ----------------
BG0 = "#0b0e14"
BG1 = "#12161f"
BG2 = "#1a2130"
CARD = "#141a26"
BORDER = "#232c3b"
TEXT = "#dce4f0"
MUTED = "#7d8ca3"
ACCENT = "#4f8cff"
ACCENT2 = "#00d4aa"
GREEN = "#0ecb81"
RED = "#f6465d"
YELLOW = "#f0b90b"
PURPLE = "#a78bfa"

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 8)
FONT_MED = ("Segoe UI", 11, "bold")
FONT_BIG = ("Segoe UI", 26, "bold")
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_MONO = ("Consolas", 10)


class AsyncBot:
    def __init__(self):
        self.bot = None
        self.loop = None
        self._thread = None
        self.started = False

    def start(self):
        if self.started:
            return
        self.started = True

        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.bot = PersonalBot()
            self.loop.run_until_complete(self.bot.start())
            self.loop.run_forever()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def run(self, coroutine, timeout=40):
        if not self.loop or not self.bot:
            return "Bot not ready"
        try:
            return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)
        except Exception as e:
            return f"Error: {e}"


def style_setup():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(".", background=BG0, foreground=TEXT, font=FONT)
    style.configure("TNotebook", background=BG0, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG1, foreground=MUTED,
                    font=("Segoe UI", 9, "bold"), padding=(16, 9), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", BG2)],
              foreground=[("selected", ACCENT)])
    style.configure("Treeview", background=BG1, fieldbackground=BG1, foreground=TEXT,
                    borderwidth=0, font=FONT, rowheight=26)
    style.map("Treeview", background=[("selected", "#1e3a6b")])
    style.configure("Treeview.Heading", background=BG2, foreground=MUTED, font=FONT_MED,
                    borderwidth=0)
    style.configure("TButton", background=BG2, foreground=TEXT, font=FONT, borderwidth=0, padding=7)
    style.map("TButton", background=[("active", ACCENT)], foreground=[("active", "#ffffff")])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", font=("Segoe UI", 10, "bold"))
    style.map("Accent.TButton", background=[("active", "#3a72d4")])
    style.configure("Danger.TButton", background=RED, foreground="#ffffff")
    style.configure("TEntry", fieldbackground=BG2, foreground=TEXT, insertcolor=ACCENT, borderwidth=0)
    style.configure("TCombobox", fieldbackground=BG2, foreground=TEXT, background=BG2, borderwidth=0)
    style.map("TCombobox", fieldbackground=[("readonly", BG2)], foreground=[("readonly", TEXT)])
    style.configure("C.TCheckbutton", background=BG0, foreground=TEXT, font=("Segoe UI", 9))
    style.map("C.TCheckbutton", background=[("active", BG0)])
    style.configure("Status.TLabel", background=BG0, foreground=MUTED, font=("Segoe UI", 9))


class Dashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Personal Bot Pro  ·  Trading Suite")
        self.root.geometry("1440x900")
        self.root.configure(bg=BG0)
        self.root.minsize(1200, 760)

        self.bot = AsyncBot()
        self.bot.start()

        self.all_coins = []
        self.search_var = tk.StringVar()
        self.current_symbol = tk.StringVar(value="BTC")
        self.current_interval = tk.StringVar(value="1h")
        self.sel_indicator = {
            "SMA": tk.BooleanVar(value=True),
            "EMA": tk.BooleanVar(value=True),
            "Bollinger": tk.BooleanVar(value=True),
        }
        self.status_var = tk.StringVar(value="Starting...")
        self.fear_greed = {"value": "--", "label": "--"}

        self._build_ui()
        self.root.after(600, self.refresh_market)
        self.root.after(800, self.load_chart)
        self.root.after(1200, self._load_fear_greed)
        self.root.after(2500, self._run_alert_loop)

    # ================= LAYOUT =================
    def _build_ui(self):
        self._build_ticker_strip()
        self._build_middle()
        self._build_statusbar()

    def _tk(self, parent, text, size=10, bold=False, color=TEXT, bg=BG0, anchor="w"):
        return tk.Label(parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"),
                        fg=color, bg=bg, anchor=anchor)

    def _card(self, parent):
        f = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        return f

    # ---------------- TOP TICKER STRIP ----------------
    def _build_ticker_strip(self):
        strip = tk.Frame(self.root, bg=BG1)
        strip.pack(fill="x")
        inner = tk.Frame(strip, bg=BG1)
        inner.pack(fill="x", padx=14, pady=6)
        tk.Label(inner, text="◈  PERSONAL BOT PRO", font=("Segoe UI", 12, "bold"),
                 fg=ACCENT, bg=BG1).pack(side="left")
        tk.Label(inner, text=" Trading Suite v3.0", font=("Segoe UI", 9), fg=MUTED,
                 bg=BG1).pack(side="left", padx=(6, 0))
        self.ticker_container = tk.Frame(inner, bg=BG1)
        self.ticker_container.pack(side="left", padx=18)
        self.ticker_labels = []
        for sym in ("BTC", "ETH", "SOL", "BNB"):
            cell = tk.Frame(self.ticker_container, bg=BG1)
            cell.pack(side="left", padx=8)
            lab = tk.Label(cell, text=f"{sym} --", font=("Consolas", 10, "bold"),
                           fg=TEXT, bg=BG1)
            lab.pack(side="left")
            self.ticker_labels.append((sym, lab))

    # ---------------- MIDDLE: SIDEBAR + MAIN ----------------
    def _build_middle(self):
        middle = tk.Frame(self.root, bg=BG0)
        middle.pack(fill="both", expand=True, padx=14, pady=10)

        self._build_sidebar(middle)

        self.notebook = ttk.Notebook(middle)
        self.notebook.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.tab_market = tk.Frame(self.notebook, bg=BG0)
        self.tab_chart = tk.Frame(self.notebook, bg=BG0)
        self.tab_scan = tk.Frame(self.notebook, bg=BG0)
        self.tab_trade = tk.Frame(self.notebook, bg=BG0)
        self.tab_alerts = tk.Frame(self.notebook, bg=BG0)
        self.tab_fb = tk.Frame(self.notebook, bg=BG0)

        self._build_market_tab()
        self._build_chart_tab()
        self._build_trade_tab()
        self._build_alert_tab()
        self._build_fb_tab()

        self.notebook.add(self.tab_market, text="Market")
        self.notebook.add(self.tab_chart, text="Chart")
        self.notebook.add(self.tab_trade, text="Auto Trade")
        self.notebook.add(self.tab_alerts, text="Alerts")
        self.notebook.add(self.tab_fb, text="Facebook Ads")

    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=BG1, width=210)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        tk.Label(side, text="MARKET OVERVIEW", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=BG1).pack(anchor="w", padx=14, pady=(14, 6))

        self.side_stats = {}
        for title, val, color in [("Fear & Greed", "--", YELLOW),
                                  ("24h Volume", "--", MUTED),
                                  ("Active Coins", "--", ACCENT)]:
            cell = tk.Frame(side, bg=BG2)
            cell.pack(fill="x", padx=10, pady=3)
            tk.Label(cell, text=title, font=FONT_SMALL, fg=MUTED, bg=BG2).pack(anchor="w", padx=8, pady=(6, 0))
            vlab = tk.Label(cell, text=val, font=("Segoe UI", 14, "bold"), fg=color, bg=BG2)
            vlab.pack(anchor="w", padx=8, pady=(0, 6))
            self.side_stats[title] = vlab

        tk.Label(side, text="QUICK ACTIONS", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=BG1).pack(anchor="w", padx=14, pady=(16, 6))
        for label, handler in [
            ("Refresh Market", self.refresh_market),
            ("Load All Coins", lambda: self.refresh_market(load_all=True)),
            ("BTC Chart", lambda: self._goto_chart("BTC")),
            ("ETH Chart", lambda: self._goto_chart("ETH")),
        ]:
            ttk.Button(side, text=label, command=handler).pack(fill="x", padx=10, pady=2)

    # ---------------- MARKET TAB ----------------
    def _build_market_tab(self):
        frame = self.tab_market

        toolbar = tk.Frame(frame, bg=BG0)
        toolbar.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(toolbar, text="Search coin:", font=FONT, fg=TEXT, bg=BG0).pack(side="left")
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=22)
        self.search_entry.pack(side="left", padx=(6, 12))
        self.search_var.trace_add("write", lambda *a: self._render_market(self.all_coins))

        tk.Label(toolbar, text="Sort:", font=FONT, fg=TEXT, bg=BG0).pack(side="left")
        self.sort_var = tk.StringVar(value="Market Cap / Volume")
        sort_cb = ttk.Combobox(toolbar, textvariable=self.sort_var, state="readonly", width=18,
                               values=("Market Cap / Volume", "Price", "24h %", "Name"))
        sort_cb.pack(side="left", padx=6)
        sort_cb.bind("<<ComboboxSelected>>", lambda e: self._render_market(self.all_coins))

        self.auto_refresh = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Auto-refresh 30s", variable=self.auto_refresh,
                        style="C.TCheckbutton").pack(side="left", padx=12)
        ttk.Button(toolbar, text="↻ Refresh", command=self.refresh_market,
                   style="Accent.TButton").pack(side="left")
        tk.Label(toolbar, text=" | double-click coin → chart",
                 font=FONT_SMALL, fg=MUTED, bg=BG0).pack(side="right")

        statrow = tk.Frame(frame, bg=BG0)
        statrow.pack(fill="x", padx=12, pady=(0, 8))
        self.market_cards = {}
        for key, title, color in [("gainers", "Top Gainers", GREEN),
                                  ("losers", "Top Losers", RED),
                                  ("volume", "Highest Volume", ACCENT),
                                  ("price", "Highest Price", YELLOW)]:
            card = self._card(statrow)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(card, text=title, font=FONT_SMALL, fg=MUTED, bg=CARD).pack(anchor="w", padx=10, pady=(8, 0))
            vlab = tk.Label(card, text="--", font=("Segoe UI", 13, "bold"), fg=color, bg=CARD)
            vlab.pack(anchor="w", padx=10, pady=(0, 8))
            self.market_cards[key] = (vlab, color)

        table_holder = tk.Frame(frame, bg=BG0)
        table_holder.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        cols = ("sym", "name", "price", "chg", "high249", "low249", "vol")
        self.tree = ttk.Treeview(table_holder, columns=cols, show="headings")
        heads = {"sym": ("Symbol", 90), "name": ("Name", 190), "price": ("Price", 130),
                 "chg": ("24h %", 100), "high249": ("24h High", 120),
                 "low249": ("24h Low", 120), "vol": ("Volume", 150)}
        for col, (t, w) in heads.items():
            self.tree.heading(col, text=t)
            self.tree.column(col, width=w, anchor="w" if col in ("sym", "name") else "e")
        self.tree.tag_configure("up", foreground=GREEN)
        self.tree.tag_configure("down", foreground=RED)
        vsb = ttk.Scrollbar(table_holder, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_tree_double)

        tk.Label(frame, textvariable=self.status_var, font=FONT_SMALL, fg=MUTED,
                 bg=BG0).pack(side="bottom", anchor="w", padx=14, pady=(0, 6))

    def _on_tree_double(self, _e):
        sel = self.tree.selection()
        if not sel:
            return
        sym = self.tree.item(sel[0], "values")[0]
        self._goto_chart(sym)

    def _goto_chart(self, symbol):
        self.current_symbol.set(symbol.replace("USDT", ""))
        self.notebook.select(self.tab_chart)
        self.load_chart()

    def refresh_market(self, load_all=False):
        self.status_var.set("Fetching market data...")
        def worker():
            data = provider.get_all_prices()
            self.root.after(0, lambda: self._on_market_data(data))
        threading.Thread(target=worker, daemon=True).start()

    def _on_market_data(self, rows):
        self.all_coins = rows
        self._render_market(rows)
        self._update_ticker(rows)
        upd = self.side_stats.get("Active Coins")
        if upd:
            upd.config(text=str(len(rows)))
        if self.auto_refresh.get():
            self.root.after(30000, self.refresh_market)

    def _update_ticker(self, rows):
        for sym, lab in self.ticker_labels:
            r = next((x for x in rows if x["symbol"] == sym), None)
            if not r:
                continue
            chg = r.get("change_24h", 0) or 0
            color = GREEN if chg >= 0 else RED
            lab.config(text=f"  {sym}  ${r['price']:,.0f}  {chg:+.1f}%", fg=color)

    def _render_market(self, rows):
        query = self.search_var.get().strip().upper()
        if query:
            rows = [r for r in rows if query in r["symbol"].upper() or query in r["name"].upper()]
        sort = self.sort_var.get()
        if sort == "Price":
            rows = sorted(rows, key=lambda r: -r["price"])
        elif sort == "24h %":
            rows = sorted(rows, key=lambda r: -(r.get("change_24h") or 0))
        elif sort == "Name":
            rows = sorted(rows, key=lambda r: r["name"].lower())
        else:
            rows = sorted(rows, key=lambda r: -(r.get("quote_volume", 0) or r.get("volume", 0) or 0))

        self.tree.delete(*self.tree.get_children())
        for r in rows[:600]:
            chg = r.get("change_24h", 0) or 0
            vol = r.get("quote_volume", 0) or r.get("volume", 0) or 0
            high = r.get("high_24h", 0) or 0
            low = r.get("low_24h", 0) or 0
            tag = "up" if chg >= 0 else "down"
            self.tree.insert("", "end", values=(
                r["symbol"], r["name"], f"${r['price']:,.2f}", f"{chg:+.2f}%",
                f"${high:,.2f}" if high else "-", f"${low:,.2f}" if low else "-",
                f"{vol:,.0f}"), tags=(tag,))

        self._update_market_cards(rows)

    def _update_market_cards(self, rows):
        gainers = sorted([r for r in rows if (r.get("change_24h") or 0) > 0],
                         key=lambda r: -(r.get("change_24h") or 0))[:1]
        losers = sorted([r for r in rows if (r.get("change_24h") or 0) < 0],
                        key=lambda r: (r.get("change_24h") or 0))[:1]
        visitors = sorted(rows, key=lambda r: -(r.get("quote_volume", 0) or r.get("volume", 0) or 0))[:1]
        pricey = sorted(rows, key=lambda r: -r["price"])[:1]
        maps = [("gainers", gainers), ("losers", losers), ("volume", visitors), ("price", pricey)]
        for key, items in maps:
            lab, color = self.market_cards.get(key, (None, None))
            if not lab:
                continue
            if items:
                item = items[0]
                extra = f"{item.get('change_24h', 0):+.1f}%" if key != "price" else ""
                lab.config(text=f"{item['symbol']}  ${item['price']:,.2f} {extra}", fg=color)
            else:
                lab.config(text="--", fg=color)

    # ---------------- CHART TAB ----------------
    def _build_chart_tab(self):
        frame = self.tab_chart
        toolbar = tk.Frame(frame, bg=BG0)
        toolbar.pack(fill="x", padx=12, pady=(12, 8))

        tk.Label(toolbar, text="Symbol:", font=FONT, fg=TEXT, bg=BG0).pack(side="left")
        combos = ttk.Combobox(toolbar, textvariable=self.current_symbol, width=9, values=DEFAULT_SYMBOLS)
        combos.pack(side="left", padx=(6, 12))
        combos.bind("<<ComboboxSelected>>", lambda e: self.load_chart())

        tk.Label(toolbar, text="TF:", font=FONT, fg=TEXT, bg=BG0).pack(side="left")
        tf_cb = ttk.Combobox(toolbar, textvariable=self.current_interval, width=6, state="readonly",
                             values=("5m", "15m", "30m", "1h", "2h", "4h", "1d"))
        tf_cb.pack(side="left", padx=(6, 14))
        tf_cb.bind("<<ComboboxSelected>>", lambda e: self.load_chart())

        for label, var in self.sel_indicator.items():
            ttk.Checkbutton(toolbar, text=label, variable=var, command=self.load_chart,
                            style="C.TCheckbutton").pack(side="left", padx=(0, 12))

        ttk.Button(toolbar, text="⟳ Reload", command=self.load_chart, style="Accent.TButton").pack(side="left")
        ttk.Button(toolbar, text="Indicators Panel", command=self._indicator_panel).pack(side="left", padx=8)

        self.signal_frame = tk.Frame(frame, bg=BG1)
        self.signal_frame.pack(fill="x", padx=12, pady=(0, 8))
        self.signal_label = tk.Label(self.signal_frame, text="Loading indicator signals...",
                                     font=("Segoe UI", 9, "bold"), fg=YELLOW, bg=BG1, anchor="w")
        self.signal_label.pack(fill="x", padx=12, pady=8)

        self.chart_frame = tk.Frame(frame, bg=BORDER)
        self.chart_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def load_chart(self):
        symbol = self.current_symbol.get().replace("USDT", "").upper()
        interval = self.current_interval.get()
        self.status_var.set(f"Loading {symbol} chart...")
        def worker():
            candles = provider.get_klines(symbol, interval, limit=150)
            if not candles:
                self.root.after(0, lambda: self.status_var.set(f"No chart data for {symbol}"))
                return
            ind = all_indicators(candles)
            summ = signal_summary(ind, candles[-1])
            self.root.after(0, lambda: self._draw_chart(symbol, interval, candles, ind, summ))
        threading.Thread(target=worker, daemon=True).start()

    def _draw_chart(self, symbol, interval, candles, ind, summ):
        for w in self.chart_frame.winfo_children():
            w.destroy()
        fig = Figure(figsize=(10, 7.2), dpi=96, facecolor=CARD)
        gs = fig.add_gridspec(6, 1, height_ratios=[4, 1.2, 1.0, 1.0, 1.0, 1.0], hspace=0.05,
                              left=0.07, right=0.97, top=0.96, bottom=0.09)

        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
        ax3 = fig.add_subplot(gs[2:4, 0], sharex=ax1)
        ax4 = fig.add_subplot(gs[4:6, 0], sharex=ax1)
        for ax in (ax1, ax2, ax3, ax4):
            ax.set_facecolor(CARD)
            ax.grid(True, color="#1f2633", linewidth=0.5)
            ax.tick_params(colors=MUTED, labelsize=8)

        times = [datetime.datetime.fromtimestamp(c["time"]) for c in candles]
        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        vols = [c["volume"] for c in candles]

        for i in range(len(candles)):
            color = GREEN if closes[i] >= opens[i] else RED
            ax1.plot([times[i], times[i]], [lows[i], highs[i]], color=color, lw=0.9)
            wick = 0.45 * (times[1] - times[0]).total_seconds() / 86400
            body_bottom = min(opens[i], closes[i])
            body_h = abs(closes[i] - opens[i])
            xi = mdates.date2num(times[i])
            ax1.add_patch(__import__("matplotlib").patches.Rectangle(
                (xi - wick / 2, body_bottom), wick, body_h or 1e-9,
                facecolor=color, edgecolor=color, lw=0.8))

        idx = list(range(len(candles)))
        if self.sel_indicator["SMA"].get():
            for p, col in ((5, YELLOW), (20, ACCENT), (50, PURPLE)):
                ser = ind[f"sma_{p}"]
                v = [i for i in idx if ser[i] is not None]
                if v:
                    ax1.plot([times[i] for i in v], [ser[i] for i in v], color=col, lw=1.3, label=f"SMA{p}")
        if self.sel_indicator["EMA"].get():
            e = ind["ema_12"]
            v = [i for i in idx if e[i] is not None]
            if v:
                ax1.plot([times[i] for i in v], [e[i] for i in v], color="#00d4ff", lw=1.2, label="EMA12")
        if self.sel_indicator["Bollinger"].get():
            up, mid, lo = ind["bollinger_20"]
            ax1.plot(times, [x if x is not None else float("nan") for x in up], color="#7d8ca3", lw=0.9, ls="--")
            ax1.plot(times, [x if x is not None else float("nan") for x in lo], color="#7d8ca3", lw=0.9, ls="--")
            ax1.plot(times, [x if x is not None else float("nan") for x in mid], color="#7d8ca3", lw=0.7)

        ax1.set_title(f"{symbol}/USD  ·  {interval}", color=TEXT, fontsize=13, fontweight="bold")
        ax1.legend(loc="upper left", fontsize=8, framealpha=0.2, facecolor=CARD, edgecolor=BORDER)
        ax1.set_xticklabels([])

        vol_colors = [("green" if opens[i] <= closes[i] else "red") for i in range(len(candles))]
        ax2.bar(times, vols, width=wick, color=[GREEN if c == "green" else RED for c in vol_colors], alpha=0.75)
        ax2.set_xticklabels([])
        ax2.set_ylabel("Vol", color=MUTED, fontsize=8)

        rsi_ser = ind["rsi_14"]
        ax3.plot(times, [x if x is not None else float("nan") for x in rsi_ser], color=PURPLE, lw=1.4)
        ax3.axhline(70, color=RED, lw=0.8, ls="--")
        ax3.axhline(30, color=GREEN, lw=0.8, ls="--")
        ax3.set_ylabel("RSI", color=MUTED, fontsize=8)
        ax3.set_ylim(0, 100)
        ax3.set_xticklabels([])

        macd_l, macd_s, macd_h = ind["macd"]
        hist_colors = [GREEN if (macd_h[i] or 0) >= 0 else RED for i in idx]
        ax4.bar(times, [x if x is not None else 0 for x in macd_h], width=wick, color=hist_colors, alpha=0.8)
        ax4.plot(times, [x if x is not None else float("nan") for x in macd_l], color=ACCENT, lw=1.2)
        ax4.plot(times, [x if x is not None else float("nan") for x in macd_s], color=YELLOW, lw=1.2)
        ax4.axhline(0, color=BORDER, lw=0.8)
        ax4.set_ylabel("MACD", color=MUTED, fontsize=8)
        ax4.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        ax4.tick_params(labelsize=8)

        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        verdict = summ["verdict"]
        color = GREEN if verdict == "BUY" else RED if verdict == "SELL" else YELLOW
        text = "Verdict: " + verdict + "   ·   " + "   ·   ".join(summ["signals"])
        self.signal_label.config(text=text, fg=color)
        self.status_var.set(f"{symbol} chart · {len(candles)} candles · {datetime.datetime.now():%H:%M:%S}")

    def _indicator_panel(self):
        symbol = self.current_symbol.get().replace("USDT", "").upper()
        win = tk.Toplevel(self.root)
        win.title(f"{symbol} - Live Indicators")
        win.geometry("460x560")
        win.configure(bg=BG0)
        tk.Label(win, text=f"{symbol}  ·  Technical Indicators", font=FONT_TITLE,
                 fg=ACCENT, bg=BG0).pack(pady=12)
        text = scrolledtext.ScrolledText(win, bg="#0e131c", fg=TEXT, font=FONT_MONO,
                                         relief="flat", padx=14, pady=14)
        text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        text.insert("end", "Loading...\n")

        def worker():
            candles = provider.get_klines(symbol, "1h", limit=100)
            if not candles:
                self.root.after(0, lambda: text.delete("1.0", "end"))
                self.root.after(0, lambda: text.insert("end", "No data"))
                return
            ind = all_indicators(candles)
            c = candles[-1]
            m_l, m_s, m_h = ind["macd"]
            upm, midm, lom = ind["bollinger_20"]
            ss = signal_summary(ind, c)
            rsi_v = ind["rsi_14"][-1]
            cell = [
                f"Symbol     : {symbol}",
                f"Price      : ${c['close']:,.4f}",
                "",
                "— Moving Averages —",
                f"  SMA 5   : {ind['sma_5'][-1]:,.4f}",
                f"  SMA 10  : {ind['sma_10'][-1]:,.4f}",
                f"  SMA 20  : {ind['sma_20'][-1]:,.4f}",
                f"  SMA 50  : {ind['sma_50'][-1]:,.4f}",
                f"  EMA 12  : {ind['ema_12'][-1]:,.4f}",
                f"  EMA 26  : {ind['ema_26'][-1]:,.4f}",
                "",
                "— Bollinger (20, 2σ) —",
                f"  Upper   : {upm[-1]:,.4f}",
                f"  Middle  : {midm[-1]:,.4f}",
                f"  Lower   : {lom[-1]:,.4f}",
                "",
                "— MACD (12,26,9) —",
                f"  MACD    : {m_l[-1]:,.4f}",
                f"  Signal  : {m_s[-1]:,.4f}",
                f"  Hist    : {m_h[-1]:,.4f}",
                "",
                "— RSI (14) —",
                f"  RSI     : {rsi_v:.2f}",
                f"  Level   : {'Oversold' if rsi_v <= 30 else 'Overbought' if rsi_v >= 70 else 'Neutral'}",
                "",
                "— Verdict —",
                f"  {ss['verdict']}",
            ]
            for s in ss["signals"]:
                cell.append(f"   • {s}")
            content = "\n".join(cell)
            self.root.after(0, lambda: text.delete("1.0", "end"))
            self.root.after(0, lambda: text.insert("end", content))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- TRADE TAB ----------------
    def _build_trade_tab(self):
        frame = self.tab_trade
        bar = tk.Frame(frame, bg=BG0)
        bar.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(bar, text="AUTOMATED TRADING", font=FONT_TITLE, fg=ACCENT, bg=BG0).pack(side="left")
        self.mode_label = tk.Label(bar, text="● PAPER MODE (safe)", font=("Segoe UI", 10, "bold"),
                                   fg=GREEN, bg=BG0)
        self.mode_label.pack(side="right")

        card = self._card(frame)
        card.pack(fill="x", padx=12, pady=(0, 10))

        r1 = tk.Frame(card, bg=CARD)
        r1.pack(fill="x", pady=6)
        tk.Label(r1, text="Coin", font=FONT, fg=TEXT, bg=CARD).grid(row=0, column=0, sticky="w", padx=4)
        self.trade_sym = tk.StringVar(value="BTC")
        ttk.Entry(r1, textvariable=self.trade_sym, width=12).grid(row=0, column=1, padx=6)
        tk.Label(r1, text="Strategy", font=FONT, fg=TEXT, bg=CARD).grid(row=0, column=2, sticky="w", padx=16)
        self.strategy_var = tk.StringVar(value="sma_cross")
        sc = ttk.Combobox(r1, textvariable=self.strategy_var, width=24, state="readonly",
                          values=("sma_cross", "rsi_mean_reversion"))
        sc.grid(row=0, column=3, padx=6)
        tk.Label(r1, text="Quantity", font=FONT, fg=TEXT, bg=CARD).grid(row=0, column=4, sticky="w", padx=16)
        self.trade_qty = tk.StringVar(value="0.0001")
        ttk.Entry(r1, textvariable=self.trade_qty, width=12).grid(row=0, column=5, padx=6)

        r2 = tk.Frame(card, bg=CARD)
        r2.pack(fill="x", pady=6)
        ttk.Button(r2, text="▶ Run Strategy", command=self._run_trade, style="Accent.TButton").pack(side="left")
        ttk.Button(r2, text="Trade Status", command=self._trade_status).pack(side="left", padx=8)
        ttk.Button(r2, text="⚠ Switch to REAL Mode", command=self._switch_real, style="Danger.TButton").pack(side="right")
        tk.Label(r2, text=" Balance ≈ $1.72  ·  Paper trading is FREE", font=FONT_SMALL,
                 fg=MUTED, bg=CARD).pack(side="right", padx=10)

        log = tk.Frame(frame, bg=BG0)
        log.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        tk.Label(log, text="TRADE LOG", font=("Segoe UI", 9, "bold"), fg=MUTED,
                 bg=BG0).pack(anchor="w", pady=4)
        self.trade_log = scrolledtext.ScrolledText(log, bg="#0e131c", fg=TEXT, font=FONT_MONO,
                                                   relief="flat", padx=12, pady=12)
        self.trade_log.pack(fill="both", expand=True)
        self.trade_log.insert("end", "Ready. Strategy runs execute trades in PAPER mode.\n")

    def _run_trade(self):
        sym = self.trade_sym.get().strip().upper()
        if not sym.endswith("USDT"):
            sym += "USDT"
        strat = self.strategy_var.get()
        self.trade_log.insert("end", f">> Running {strat} on {sym} (paper)\n")
        self.trade_log.see("end")
        def worker():
            try:
                res = self.bot.run(self.bot.bot.trader.run_once(sym, strat), timeout=50)
            except Exception as e:
                res = f"Error: {e}"
            self.root.after(0, lambda: self.trade_log.insert("end", str(res) + "\n\n"))
        threading.Thread(target=worker, daemon=True).start()

    def _trade_status(self):
        def worker():
            res = self.bot.run(self.bot.bot.trader.get_status())
            self.root.after(0, lambda: self.trade_log.insert("end", "STATUS:\n" + str(res) + "\n\n"))
        threading.Thread(target=worker, daemon=True).start()

    def _switch_real(self):
        def worker():
            self.bot.run(self.bot.bot.market_agent.execute({"type": "set_test_mode", "test_mode": False}))
            self.root.after(0, lambda: self.mode_label.config(text="● REAL MODE — REAL MONEY", fg=RED))
        threading.Thread(target=worker, daemon=True).start()

    # ---------------- ALERT TAB ----------------
    def _build_alert_tab(self):
        frame = self.tab_alerts
        card = self._card(frame)
        card.pack(fill="x", padx=12, pady=12)
        tk.Label(card, text="PRICE ALERTS", font=("Segoe UI", 10, "bold"), fg=ACCENT,
                 bg=CARD).pack(anchor="w", padx=10, pady=(10, 4))
        r = tk.Frame(card, bg=CARD)
        r.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(r, text="Coin", font=FONT, fg=TEXT, bg=CARD).pack(side="left")
        self.alert_sym = tk.StringVar(value="BTC")
        sym_cb = ttk.Combobox(r, textvariable=self.alert_sym,
                              width=9, values=DEFAULT_SYMBOLS)
        sym_cb.pack(side="left", padx=6)
        self.alert_cond = tk.StringVar(value="above")
        cond_cb = ttk.Combobox(r, textvariable=self.alert_cond,
                               width=8, state="readonly", values=("above", "below"))
        cond_cb.pack(side="left", padx=6)
        self.alert_price_var = tk.StringVar(value="90000")
        ttk.Entry(r, textvariable=self.alert_price_var, width=12).pack(side="left", padx=6)
        ttk.Button(r, text="＋ Create", command=self._create_alert, style="Accent.TButton").pack(side="left", padx=6)
        ttk.Button(r, text="Check Now", command=self._check_alerts).pack(side="left", padx=6)

        self.alert_box = scrolledtext.ScrolledText(frame, bg="#0e131c", fg=TEXT,
                                                   font=FONT_MONO, relief="flat", padx=12, pady=12)
        self.alert_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.alert_box.insert("end", "No alerts. Add one above - bot checks every 45s.\n")

    def _create_alert(self):
        sym = self.alert_sym.get().upper()
        cond = self.alert_cond.get()
        try:
            price = float(self.alert_price_var.get())
        except ValueError:
            return
        a = self.bot.bot.alerts.add_alert(sym + "USDT", cond, price, f"{sym} {cond} {price}")
        self.alert_box.insert("end", f"CREATED {a['alert_id']}  {sym} {cond} ${price:,.2f}\n")
        self.alert_box.see("end")

    def _check_alerts(self):
        def worker():
            try:
                res = self.bot.run(self.bot.bot.alerts.check_all())
                if res:
                    for a in res:
                        msg = f"⚡ TRIGGERED {a['symbol']} {a['condition']} ${a['target_price']:,.2f} → ${a['current_price']:,.2f}\n"
                        self.root.after(0, lambda m=msg: self.alert_box.insert("end", m))
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    # ---------------- FACEBOOK TAB ----------------
    def _build_fb_tab(self):
        frame = self.tab_fb
        bar = tk.Frame(frame, bg=BG0)
        bar.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(bar, text="FACEBOOK ADS MANAGER", font=FONT_TITLE, fg=ACCENT, bg=BG0).pack(side="left")
        ttk.Button(bar, text="▲ Refresh Campaigns", command=self._fb_list).pack(side="right")
        ttk.Button(bar, text="Insights (7d)", command=self._fb_insights).pack(side="right", padx=(0, 8))

        cols = ("id", "name", "status", "obj", "budget", "start")
        self.fb_tree = ttk.Treeview(frame, columns=cols, show="headings", height=9)
        hs = {"id": ("Campaign ID", 160), "name": ("Name", 320), "status": ("Status", 90),
              "obj": ("Objective", 150), "budget": ("Budget $/day", 100), "start": ("Start", 150)}
        for col, (t, w) in hs.items():
            self.fb_tree.heading(col, text=t)
            self.fb_tree.column(col, width=w, anchor="w")
        self.fb_tree.pack(fill="x", padx=12, pady=(0, 8))

        n = tk.Frame(frame, bg=BG0)
        n.pack(fill="x", padx=12, pady=(0, 8))
        self.fb_id_var = tk.StringVar()
        ttk.Entry(n, textvariable=self.fb_id_var, width=24).pack(side="left", padx=(0, 8))
        ttk.Button(n, text="Pause", command=lambda: self._fb_action("pause_campaign")).pack(side="left", padx=3)
        ttk.Button(n, text="Resume", command=lambda: self._fb_action("resume_campaign")).pack(side="left", padx=3)
        ttk.Button(n, text="Scale +20%", command=self._fb_scale).pack(side="left", padx=3)
        tk.Label(n, text="(paste campaign ID)", font=FONT_SMALL, fg=MUTED, bg=BG0).pack(side="left", padx=8)

        self.fb_log = scrolledtext.ScrolledText(frame, bg="#0e131c", fg=TEXT, font=FONT_MONO,
                                                relief="flat", padx=12, pady=12)
        self.fb_log.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.root.after(1600, self._fb_list)

    def _fb_log_error(self, res, prefix=""):
        if isinstance(res, dict) and res.get("error"):
            msg = res["error"]
            if isinstance(msg, str) and "***" in msg:
                msg = "Connection failed (SSL/network). Check your internet."
            self.fb_log.insert("end", f"⚠ {prefix}{msg}\n\n")
            return True
        return False

    def _fb_list(self):
        def worker():
            try:
                res = self.bot.run(
                    self.bot.bot.orchestrator.agents["facebook_ads"].safe_execute({"type": "list_campaigns"}),
                    timeout=40,)
                camps = []
                if isinstance(res, dict):
                    camps = res.get("data", {}).get("campaigns", []) or res.get("campaigns", [])
                self.root.after(0, lambda: self._render_fb(camps, res))
            except Exception as e:
                self.root.after(0, lambda: self.fb_log.insert("end", f"ERR {e}\n\n"))
        threading.Thread(target=worker, daemon=True).start()

    def _render_fb(self, camps, raw):
        self.fb_tree.delete(*self.fb_tree.get_children())
        if not camps:
            self._fb_log_error(raw, "Facebook Ads: ")
            return
        for c in camps:
            self.fb_tree.insert("", "end", values=(
                c.get("id"), c.get("name", "?"), c.get("status"), c.get("objective"),
                float(c.get("daily_budget") or 0) / 100, (c.get("start_time") or "")[:10]))
        self.fb_log.insert("end", f"✓ Loaded {len(camps)} campaigns\n")

    def _fb_insights(self):
        def worker():
            try:
                res = self.bot.run(
                    self.bot.bot.orchestrator.agents["facebook_ads"].safe_execute({"type": "get_insights"}),
                    timeout=40)
                self.root.after(0, lambda: self._fb_render_insights(res))
            except Exception as e:
                self.root.after(0, lambda: self.fb_log.insert("end", f"ERR {e}\n\n"))
        threading.Thread(target=worker, daemon=True).start()

    def _fb_render_insights(self, res):
        if not isinstance(res, dict):
            self.fb_log.insert("end", f"INSIGHTS: {res}\n\n")
            return
        err = res.get("error")
        if err:
            self._fb_log_error(res, "Insights: ")
            return
        rows = res.get("data", res)
        if isinstance(rows, dict):
            rows = rows.get("insights") or rows.get("data") or []
        if isinstance(rows, list) and rows:
            for r in rows[:10]:
                line = (f"{r.get('date_start','')} →"
                        f" spend ${r.get('spend','?')} · imp {r.get('impressions','?')}"
                        f" · CTR {r.get('ctr','?')} · ROAS {r.get('return_on_ad_spend','?')}\n")
                self.fb_log.insert("end", line)
            self.fb_log.insert("end", "\n")
        else:
            self.fb_log.insert("end", f"INSIGHTS: {str(res)[:200]}\n\n")

    def _fb_action(self, action):
        cid = self.fb_id_var.get().strip()
        if not cid:
            return
        def worker():
            try:
                res = self.bot.run(
                    self.bot.bot.orchestrator.agents["facebook_ads"].safe_execute(
                        {"type": action, "campaign_id": cid}), timeout=40)
                self.root.after(0, lambda: self._fb_log_result(res, action))
            except Exception as e:
                self.root.after(0, lambda: self.fb_log.insert("end", f"ERR {e}\n\n"))
        threading.Thread(target=worker, daemon=True).start()

    def _fb_scale(self):
        cid = self.fb_id_var.get().strip()
        if not cid:
            return
        def worker():
            try:
                res = self.bot.run(
                    self.bot.bot.orchestrator.agents["facebook_ads"].safe_execute(
                        {"type": "scale_campaign", "campaign_id": cid, "scale_factor": 1.2}), timeout=40)
                self.root.after(0, lambda: self._fb_log_result(res, "scale"))
            except Exception as e:
                self.root.after(0, lambda: self.fb_log.insert("end", f"ERR {e}\n\n"))
        threading.Thread(target=worker, daemon=True).start()

    def _fb_log_result(self, res, label):
        if not self._fb_log_error(res, f"{label}: "):
            self.fb_log.insert("end", f"✓ {label} completed\n\n")

    # ---------------- STATUS BAR ----------------
    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG1)
        bar.pack(side="bottom", fill="x")
        tk.Label(bar, textvariable=self.status_var, font=FONT_SMALL, fg=MUTED,
                 bg=BG1).pack(side="left", padx=12, pady=4)

    def _load_fear_greed(self):
        import requests, urllib3
        urllib3.disable_warnings()
        def worker():
            try:
                r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=12, verify=False)
                d = r.json()
                val = d["data"][0]["value"]
                cl = d["data"][0]["value_classification"]
                self.fear_greed = {"value": val, "label": cl}
                color = GREEN if int(val) >= 60 else RED if int(val) <= 40 else YELLOW
                def upd():
                    lab = self.side_stats.get("Fear & Greed")
                    if lab:
                        lab.config(text=f"{val} · {cl}", fg=color)
                self.root.after(0, upd)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _run_alert_loop(self):
        self._check_alerts()
        self.root.after(45000, self._run_alert_loop)


def main():
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()