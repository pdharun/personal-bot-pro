"""Personal Bot Pro - Web Dashboard (Flask)

Deployed on a free cloud (Render.com) host. The web app is deliberately
PAPER-ONLY for trading: it can scan signals and manage price alerts but
never places real orders.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, make_response, redirect, request, send_from_directory

from config.settings import config
from tools.market_data import provider
from tools.indicators import all_indicators, signal_summary
from tools.trade_engine import engine as trade_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("webui")

APP_PASSWORD = os.getenv("APP_PASSWORD", "123@123@123")
APP_SECRET = os.getenv("APP_SECRET", "pb-pro-secret")
COOKIE_NAME = "pb_auth"


def session_token() -> str:
    return hmac.new(APP_SECRET.encode(), APP_PASSWORD.encode(), hashlib.sha256).hexdigest()


app = Flask(__name__)

web_alerts = {"items": [], "triggered": []}
_cache: Dict[str, tuple] = {}


def cached(key: str, ttl: float, producer) -> Any:
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = producer()
    _cache[key] = (now, value)
    return value


def get_fear_greed() -> Dict:
    def _load() -> Dict:
        try:
            import requests
            import urllib3
            urllib3.disable_warnings()
            r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10, verify=False)
            d = r.json()
            row = d["data"][0]
            return {"value": row["value"], "label": row["value_classification"]}
        except Exception:
            return {"value": "--", "label": "n/a"}
    return cached("fng", 120, _load)


# ---------------- AUTH ----------------
@app.before_request
def _guard():
    if request.path.startswith("/static") or request.path in ("/login", "/favicon.ico"):
        return None
    if request.cookies.get(COOKIE_NAME) != session_token():
        if request.path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return redirect("/login")
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == APP_PASSWORD:
            resp = make_response(redirect("/"))
            resp.set_cookie(COOKIE_NAME, session_token(), max_age=60 * 60 * 24 * 7, httponly=True, samesite="Lax")
            return resp
        return LOGIN_HTML.replace("<!--msg-->", '<p class="err">Wrong password</p>')
    return LOGIN_HTML


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


# ---------------- API: HEALTH ----------------
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "time": int(time.time()),
                    "fear_greed": get_fear_greed(),
                    "pap_mode": "only signals + alerts (no real orders)"})


# ---------------- API: MARKET ----------------
@app.route("/api/market")
def api_market():
    def _load():
        rows = provider.get_all_prices()
        for r in rows:
            for k in ("high_24h", "low_24h", "quote_volume"):
                r.setdefault(k, 0)
        rows.sort(key=lambda r: -(r.get("quote_volume") or 0))
        return rows
    rows = cached("market", 15, _load)
    limit = min(int(request.args.get("limit", 300)), 1500)
    return jsonify({
        "count": len(rows),
        "fear_greed": get_fear_greed(),
        "coins": rows[:limit],
    })


# ---------------- API: CHART ----------------
@app.route("/api/chart")
def api_chart():
    symbol = request.args.get("symbol", "BTC").replace("USDT", "").upper()
    interval = request.args.get("interval", "1h")
    candles = provider.get_klines(symbol, interval, 150)
    if not candles:
        return jsonify({"error": f"No chart data for {symbol}"}), 404
    ind = all_indicators(candles)
    summ = signal_summary(ind, candles[-1])

    def series(_k, default=0.0):
        raw = ind.get(_k) if isinstance(_k, str) else _k
        if raw is None:
            return []
        if not isinstance(raw, (list, tuple)):
            return []
        return [round(float(x), 6) if x is not None else default for x in raw]

    boll = ind.get("bollinger_20")
    macd = ind.get("macd")
    return jsonify({
        "symbol": symbol,
        "interval": interval,
        "last_price": candles[-1]["close"],
        "candles": candle_slim(candles),
        "sma5": series("sma_5"), "sma10": series("sma_10"),
        "sma20": series("sma_20"), "sma50": series("sma_50"),
        "ema12": series("ema_12"), "ema26": series("ema_26"),
        "boll_up": series(boll[0]) if boll else [],
        "boll_mid": series(boll[1]) if boll else [],
        "boll_lo": series(boll[2]) if boll else [],
        "rsi14": series("rsi_14"),
        "macd_l": series(macd[0]) if macd else [],
        "macd_s": series(macd[1]) if macd else [],
        "macd_h": series(macd[2]) if macd else [],
        "verdict": summ.get("verdict", "HOLD"),
        "signals": summ.get("signals", []),
    })


def candle_slim(candles: List[Dict]) -> List[Dict]:
    return [{"t": c["time"], "o": c["open"], "h": c["high"],
             "l": c["low"], "c": c["close"], "v": c["volume"]} for c in candles]


# ---------------- API: ALERTS (PAPER / notifications only) ----------------
@app.route("/api/alerts", methods=["GET", "POST"])
def alerts_api():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        symbol = str(body.get("symbol", "")).upper()
        condition = body.get("condition", "above")
        try:
            price = float(body.get("target_price"))
        except (TypeError, ValueError):
            return jsonify({"error": "target_price required"}), 400
        if condition not in ("above", "below"):
            return jsonify({"error": "condition must be above/below"}), 400
        a = {"id": f"al{int(time.time() * 1000)}", "symbol": symbol,
             "condition": condition, "target_price": price, "active": True,
             "created_at": time.time()}
        web_alerts["items"].append(a)
        return jsonify(a)
    return jsonify({"alerts": [a for a in web_alerts["items"] if a["active"]],
                    "triggered": web_alerts["triggered"][-10:]})


@app.route("/api/alerts/delete", methods=["POST"])
def alerts_delete():
    body = request.get_json(silent=True) or {}
    aid = body.get("id")
    for a in web_alerts["items"]:
        if a["id"] == aid:
            a["active"] = False
            return jsonify({"deleted": True})
    return jsonify({"error": "not found"}), 404


@app.route("/api/alerts/check", methods=["POST"])
def alerts_check():
    triggered = []
    active = [a for a in web_alerts["items"] if a["active"]]
    for a in active:
        try:
            data = provider.get_price(a["symbol"])
            price = data and data.get("price")
            if price is None:
                continue
            hit = (price >= a["target_price"]) if a["condition"] == "above" else (price <= a["target_price"])
            if hit:
                a["active"] = False
                rec = {**a, "current_price": price, "triggered_at": int(time.time())}
                web_alerts["triggered"].append(rec)
                triggered.append(rec)
        except Exception:
            continue
    return jsonify({"triggered": triggered, "active": len([a for a in web_alerts["items"] if a["active"]])})


# ---------------- API: SIGNALS (PAPER ONLY - never places orders) ----------------
@app.route("/api/signals")
def api_signals():
    symbol = request.args.get("symbol", "BTC").replace("USDT", "").upper()
    interval = request.args.get("interval", "1h")
    candles = provider.get_klines(symbol, interval, 100)
    if not candles:
        return jsonify({"error": f"No data for {symbol}"}), 404
    ind = all_indicators(candles)
    c = candles[-1]
    summ = signal_summary(ind, c)
    rsi = ind.get("rsi_14")
    return jsonify({
        "symbol": symbol,
        "interval": interval,
        "last_price": c["close"],
        "verdict": summ.get("verdict", "HOLD"),
        "signals": summ.get("signals", []),
        "rsi": round(float(rsi[-1]), 2) if rsi and rsi[-1] is not None else None,
        "paper_only": True,
    })


# ---------------- API: AUTO TRADE ENGINE ----------------
@app.route("/api/trade/start", methods=["POST"])
def trade_start():
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "paper")
    symbols = body.get("symbols")
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.replace(",", " ").split() if s.strip()]
    interval = body.get("interval", "5m")
    try:
        scan_every = float(body.get("scan_every", 60))
        notional = float(body.get("notional", 10))
    except (TypeError, ValueError):
        return jsonify({"error": "scan_every/notional must be numbers"}), 400
    sl = body.get("sl_percent")
    tp = body.get("tp_percent")
    try:
        sl = float(sl) if sl not in (None, "") else None
        tp = float(tp) if tp not in (None, "") else None
    except ValueError:
        return jsonify({"error": "sl_percent/tp_percent must be numbers"}), 400
    api_key = body.get("api_key") or (config.market.binance_api_key if mode == "real" else "")
    api_secret = body.get("api_secret") or (config.market.binance_api_secret if mode == "real" else "")
    res = trade_engine.start(
        mode=mode, symbols=symbols, interval=interval, scan_every=scan_every,
        notional=notional, sl_percent=sl, tp_percent=tp,
        api_key=api_key, api_secret=api_secret, real_confirm=body.get("real_confirm", ""),
    )
    return jsonify({"ok": res["ok"], "error": res.get("error"), "state": res.get("state")}), \
        (200 if res["ok"] else 400)


@app.route("/api/trade/stop", methods=["POST"])
def trade_stop():
    res = trade_engine.stop()
    return jsonify({"ok": True, "state": res["state"]})


@app.route("/api/trade/status")
def trade_status():
    return jsonify(trade_engine.snapshot())


@app.route("/api/trade/log")
def trade_log():
    since = request.args.get("since", 0, type=float)
    return jsonify({"logs": trade_engine.log_after(since)})


# ---------------- API: FACEBOOK ADS ----------------
fb = None


def get_fb():
    global fb
    if fb is None:
        from agents.facebook_ads_agent import FacebookAdsAgent
        fb = FacebookAdsAgent(config)
    return fb


def fb_execute(task: Dict) -> Dict:
    return asyncio.run(get_fb().execute(task))


@app.route("/api/fb/campaigns")
def fb_campaigns():
    if not config.facebook.access_token:
        return jsonify({"error": "No FB_ACCESS_TOKEN configured", "code": 0}), 200
    res = fb_execute({"type": "list_campaigns"})
    return jsonify(res)


@app.route("/api/fb/insights")
def fb_insights():
    if not config.facebook.access_token:
        return jsonify({"error": "No FB_ACCESS_TOKEN configured", "code": 0}), 200
    res = fb_execute({"type": "get_insights"})
    return jsonify(res)


@app.route("/api/fb/action", methods=["POST"])
def fb_action():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    cid = body.get("campaign_id")
    if action not in ("pause_campaign", "resume_campaign", "scale_campaign"):
        return jsonify({"error": "invalid action"}), 400
    if not cid:
        return jsonify({"error": "campaign_id required"}), 400
    task = {"type": action, "campaign_id": cid}
    if action == "scale_campaign":
        task["scale_factor"] = 1.2
    res = fb_execute(task)
    return jsonify(res)


LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Personal Bot Pro · Login</title><style>
body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#0b0e14;color:#dce4f0;
display:flex;align-items:center;justify-content:center;height:100vh}
.card{background:#12161f;border:1px solid #232c3b;border-radius:14px;padding:38px 42px;width:320px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
h1{font-size:20px;margin:0 0 4px;color:#4f8cff}.sub{color:#7d8ca3;font-size:13px;margin-bottom:22px}
input{width:100%;box-sizing:border-box;background:#1a2130;border:1px solid #232c3b;color:#dce4f0;
padding:12px;border-radius:8px;font-size:15px;margin-bottom:14px;outline:none}
input:focus{border-color:#4f8cff}
button{width:100%;background:#4f8cff;color:#fff;border:0;padding:12px;border-radius:8px;font-size:15px;
font-weight:700;cursor:pointer}button:hover{background:#3a72d4}
.err{color:#f6465d;font-size:13px;margin:0 0 12px}
</style></head><body><form class="card" method="post">
<h1>◈ Personal Bot Pro</h1><div class="sub">Trading Suite &middot; secure area</div>
<!--msg--><input type="password" name="password" placeholder="Password" required autofocus>
<button type="submit">Unlock Dashboard</button></form></body></html>"""


if __name__ == "__main__":
    if APP_PASSWORD == "123@123@123":
        logger.warning("APP_PASSWORD is the default. Change it via env in production.")
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)