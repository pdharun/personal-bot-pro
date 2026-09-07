"""Trade engine for the web dashboard.

Runs in a background thread. Deliberately PAPER by default: it tracks a
virtual wallet and never moves real money unless EXPLICITLY switched to
REAL mode (which additionally requires real_confirm="YES" on start).
Every action is appended to a thread-safe event log so the dashboard can
show what the bot is doing in real time, and a kill switch can stop it
within ~1 second.
"""
import hashlib
import hmac
import logging
import threading
import time
import urllib.parse
from collections import deque
from typing import Any, Dict, List, Optional

import requests

from tools.indicators import all_indicators, signal_summary
from tools.market_data import provider

logger = logging.getLogger(__name__)

API_BASE = "https://api.binance.com"


class TradeEngine:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_scan = 0.0
        self._started_at: Optional[float] = None

        self.mode = "paper"                       # "paper" | "real"
        self.symbols: List[str] = ["BTC", "ETH", "SOL", "BNB"]
        self.interval = "5m"
        self.scan_every = 60.0                    # seconds between scans
        self.notional = 10.0                      # USD per BUY
        self.sl_percent: Optional[float] = None   # e.g. 5  => -5% stop-loss
        self.tp_percent: Optional[float] = None   # e.g. 12 => +12% take-profit

        self.cash = 1000.0
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trades: deque = deque(maxlen=100)
        self.log: deque = deque(maxlen=500)
        self.real_balances: List[Dict] = []
        self.real_balance_ts: float = 0.0
        self.api_key = ""
        self.api_secret = ""

    # ---------------- public control ----------------
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._stop.is_set()

    def start(self, *, mode: str = "paper", symbols: Optional[List[str]] = None,
              interval: str = "5m", scan_every: float = 60.0, notional: float = 10.0,
              sl_percent: Optional[float] = None, tp_percent: Optional[float] = None,
              api_key: str = "", api_secret: str = "", real_confirm: str = "") -> Dict:
        with self._lock:
            if self.is_running():
                return {"ok": False, "error": "Engine already running"}
            mode = (mode or "paper").lower()
            if mode == "real":
                if real_confirm != "YES":
                    return {"ok": False, "error": "Real mode needs real_confirm=\"YES\""}
                if not api_key or not api_secret:
                    return {"ok": False, "error": "Real mode needs Binance API key + secret"}
            self.mode = mode
            if symbols:
                self.symbols = [s.upper().replace("USDT", "") for s in symbols if s.strip()]
            self.interval = interval or "5m"
            self.scan_every = max(5.0, float(scan_every or 60.0))
            self.notional = max(1.0, float(notional or 10.0))
            self.sl_percent = float(sl_percent) if sl_percent else None
            self.tp_percent = float(tp_percent) if tp_percent else None
            self.api_key = api_key or ""
            self.api_secret = api_secret or ""

            self._stop.clear()
            self._last_scan = 0.0
            self._started_at = time.time()
            self._thread = threading.Thread(target=self._run, name="trade-engine", daemon=True)
            self._thread.start()
            self._emit("info", f"AUTO TRADE STARTED  ·  mode={self.mode.upper()}  ·  "
                               f"{len(self.symbols)} coins  ·  every {int(self.scan_every)}s")
            return {"ok": True, "state": self.snapshot()}

    def stop(self) -> Dict:
        with self._lock:
            self._stop.set()
            msg = "STOP SWITCH PRESSED - engine stopping"
            self._emit("warn", msg)
        if self._thread:
            self._thread.join(timeout=10)
        return {"ok": True, "state": self.snapshot()}

    # ---------------- snapshot / log ----------------
    def _emit(self, level: str, msg: str):
        entry = {"ts": time.time(), "t": self._fmt_time(), "level": level, "msg": msg}
        with self._lock:
            self.log.append(entry)

    @staticmethod
    def _fmt_time(t: Optional[float] = None) -> str:
        return time.strftime("%H:%M:%S", time.localtime(t or time.time()))

    def log_after(self, since: float) -> List[Dict]:
        with self._lock:
            return [e for e in self.log if e["ts"] > since]

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            value = 0.0
            for sym, p in self.positions.items():
                value += p["qty"] * p["last"]
            equity = self.cash + value
            realized = sum(t["pnl"] for t in self.trades)
            return {
                "state": "running" if self.is_running() else "stopped",
                "mode": self.mode,
                "symbols": list(self.symbols),
                "interval": self.interval,
                "scan_every": int(self.scan_every),
                "notional": round(self.notional, 2),
                "sl_percent": self.sl_percent,
                "tp_percent": self.tp_percent,
                "started_at": self._started_at,
                "last_scan": self._last_scan,
                "cash": round(self.cash, 2),
                "positions": [
                    {"symbol": p["symbol"], "qty": p["qty"], "entry": p["entry"],
                     "last": p["last"], "pnl": round((p["last"] - p["entry"]) * p["qty"], 2),
                     "pnl_pct": round((p["last"] / p["entry"] - 1) * 100, 2),
                     "opened": p["opened"]}
                    for p in self.positions.values()
                ],
                "equity": round(equity, 2),
                "realized_pnl": round(realized, 2),
                "unrealized_pnl": round(equity - self.cash, 2),
                "trades": list(reversed(list(self.trades)))[:25],
                "log_tail": list(reversed(list(self.log)))[:60],
                "real_balances": list(self.real_balances),
                "wallet_note": "PAPER wallet (virtual)" if self.mode == "paper" else "REAL Binance account",
            }

    # ---------------- engine loop ----------------
    def _run(self):
        while not self._stop.is_set():
            now = time.time()
            if now - self._last_scan >= self.scan_every:
                try:
                    self._scan()
                except Exception as e:
                    logger.exception("scan error")
                    self._emit("error", f"Scan error: {e}")
                self._last_scan = time.time()
            self._stop.wait(0.5)

    def _scan(self):
        with self._lock:
            syms = list(self.symbols)
            interval = self.interval
            api_key = self.api_key
            api_secret = self.api_secret
        for sym in syms:
            if self._stop.is_set():
                return
            self._scan_symbol(sym, interval, api_key, api_secret)

    def _scan_symbol(self, sym: str, interval: str, api_key: str, api_secret: str):
        candles = provider.get_klines(sym, interval, 150)
        if not candles:
            self._emit("warn", f"{sym}: no data")
            return
        last = candles[-1]["close"]
        ind = all_indicators(candles)
        summ = signal_summary(ind, candles[-1])
        verdict = summ.get("verdict", "HOLD")
        rsi = ind["rsi_14"][-1]
        with self._lock:
            pos = self.positions.get(sym)

        if verdict == "BUY":
            if pos is None:
                self._open_pos(sym, last, api_key, api_secret)
            else:
                self._emit("info", f"{sym} @{last:g}  ·  BUY signal but already in position (hold)")
        elif verdict == "SELL":
            if pos is not None:
                self._close_pos(sym, last, api_key, api_secret, reason="sell signal")
            else:
                self._emit("info", f"{sym} @{last:g}  ·  SELL signal (no position)")
        else:
            self._emit("info", f"{sym} @{last:g}  ·  RSI {rsi:.1f}  ·  HOLD")

        if pos is not None and self._stop.is_set():
            return

        # SL / TP check on open positions (both modes)
        with self._lock:
            pos = self.positions.get(sym)
        if pos is not None and (self.sl_percent or self.tp_percent):
            ret = last / pos["entry"] - 1
            if self.sl_percent and ret <= -self.sl_percent / 100:
                self._close_pos(sym, last, api_key, api_secret, reason=f"STOP-LOSS {-self.sl_percent:.0f}%")
            elif self.tp_percent and ret >= self.tp_percent / 100:
                self._close_pos(sym, last, api_key, api_secret, reason=f"TAKE-PROFIT +{self.tp_percent:.0f}%")

    # ---------------- execution ----------------
    def _open_pos(self, sym: str, price: float, api_key: str, api_secret: str):
        with self._lock:
            mode = self.mode
        qty = self.notional / price
        if mode == "real":
            free = self._real_balance_usdt(api_key, api_secret)
            if free < self.notional:
                self._emit("error", f"{sym}: REAL BUY SKIPPED - USDT balance {free:.2f} < trade size {self.notional:.2f}")
                return
            res = self._real_order(sym, "BUY", qty, api_key, api_secret)
            if not res.get("ok"):
                self._emit("error", f"{sym}: REAL BUY failed - {res.get('error')}")
                return
            with self._lock:
                self.cash = free - self.notional
        else:
            with self._lock:
                if self.cash < self.notional:
                    self._emit("error", f"{sym}: PAPER BUY SKIPPED - wallet {self.cash:.2f} < trade size {self.notional:.2f}")
                    return
                self.cash -= self.notional

        with self._lock:
            self.positions[sym] = {
                "symbol": sym, "qty": qty, "entry": price, "last": price,
                "opened": self._fmt_time(),
            }
        self._emit("buy", f"OPEN {sym}  qty {qty:.6f} @ {price:g}  (${self.notional:.2f})")

    def _close_pos(self, sym: str, price: float, api_key: str, api_secret: str, reason: str):
        with self._lock:
            pos = self.positions.pop(sym, None)
        if pos is None:
            return
        pnl = (price - pos["entry"]) * pos["qty"]
        pnl_pct = (price / pos["entry"] - 1) * 100
        if self.mode == "real":
            res = self._real_order(sym, "SELL", pos["qty"], api_key, api_secret)
            if not res.get("ok"):
                self._emit("error", f"{sym}: REAL SELL failed - {res.get('error')}")
                return
        else:
            with self._lock:
                self.cash += pos["qty"] * price
        with self._lock:
            self.trades.append({
                "symbol": sym, "qty": pos["qty"], "entry": pos["entry"], "exit": price,
                "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2), "reason": reason,
                "mode": self.mode, "time": self._fmt_time(),
            })
        self._emit("sell", f"CLOSE {sym}  @ {price:g}  ·  {reason}  ·  P&L {pnl:+.2f} ({pnl_pct:+.1f}%)")

    # ---------------- Binance (REAL mode) ----------------
    def _get_config(self):
        try:
            from config.settings import config
            return config.market.binance_api_key, config.market.binance_api_secret
        except Exception:
            return "", ""

    def _signed(self, method: str, path: str, params: Dict, api_key: str, api_secret: str) -> Dict:
        params = dict(params)
        params["timestamp"] = int(time.time() * 1000)
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        url = f"{API_BASE}{path}?{qs}&signature={sig}"
        resp = requests.request(method, url, headers={"X-MBX-APIKEY": api_key}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _real_balance_usdt(self, api_key: str, api_secret: str) -> float:
        try:
            acc = self._signed("GET", "/api/v3/account", {}, api_key, api_secret)
            free = 0.0
            balances = []
            for b in acc.get("balances", []):
                if float(b.get("free") or 0) > 0:
                    balances.append({"asset": b["asset"], "free": float(b["free"])})
                    if b["asset"] == "USDT":
                        free = float(b["free"])
            with self._lock:
                self.real_balances = balances
                self.real_balance_ts = time.time()
            return free
        except Exception as e:
            self._emit("error", f"Balance check failed: {e}")
            return 0.0

    def _real_order(self, sym: str, side: str, qty: float, api_key: str, api_secret: str) -> Dict:
        try:
            res = self._signed("POST", "/api/v3/order",
                               {"symbol": sym + "USDT", "side": side, "type": "MARKET", "quantity": qty},
                               api_key, api_secret)
            return {"ok": True, **res}
        except Exception as e:
            return {"ok": False, "error": str(e)}


engine = TradeEngine()