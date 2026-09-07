import hashlib
import hmac
import logging
import time
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List

import requests

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class MarketAgent(BaseAgent):
    def __init__(self, config=None):
        super().__init__("Market", config)
        self.api_base = "https://api.binance.com"
        self.api_key = (config.market.binance_api_key if config else "") or ""
        self.api_secret = (config.market.binance_api_secret if config else "") or ""
        self.watchlist: List[Dict] = []
        self.price_history: Dict[str, List] = {}
        self.last_prices: Dict[str, Dict] = {}
        self.test_mode = True
        self.open_orders: List[Dict] = []

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("type")
        handlers = {
            "check_binance": self._check_binance_price,
            "check_dse": self._check_dse,
            "add_to_watchlist": self._add_to_watchlist,
            "get_portfolio_status": self._get_portfolio_status,
            "set_price_alert": self._set_price_alert,
            "analyze_trend": self._analyze_trend,
            "get_market_data": self._get_market_data,
            "place_order": self._place_order,
            "get_account_info": self._get_account_info,
            "set_test_mode": self._set_test_mode,
        }
        handler = handlers.get(action)
        if handler:
            return await handler(task)
        return {"error": f"Unknown action: {action}"}

    async def analyze(self, data: Any) -> Dict[str, Any]:
        return {
            "market_status": "monitoring",
            "watchlist_count": len(self.watchlist),
            "alerts_active": 0,
            "recommendations": [
                "Monitor BTC resistance at key levels",
                "Check DSE index trend",
                "Review portfolio allocation",
            ],
        }

    def _public_request(self, path: str, params: Dict = None) -> Dict:
        url = f"{self.api_base}{path}"
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _signed_request(self, method: str, path: str, params: Dict = None) -> Dict:
        if not self.api_key or not self.api_secret:
            return {"error": "Binance API key/secret not configured in config/.env"}
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        query_string += f"&signature={signature}"
        url = f"{self.api_base}{path}?{query_string}"
        headers = {"X-MBX-APIKEY": self.api_key}
        resp = requests.request(method, url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    async def _check_binance_price(self, task: Dict) -> Dict:
        symbol = task.get("symbol", "BTCUSDT").upper()
        try:
            data = self._public_request("/api/v3/ticker/price", {"symbol": symbol})
            price = float(data.get("price", 0))

            try:
                ticker = self._public_request("/api/v3/ticker/24hr", {"symbol": symbol})
                change_24h = float(ticker.get("priceChangePercent", 0))
                volume = ticker.get("volume", "0")
                high = ticker.get("highPrice", "0")
                low = ticker.get("lowPrice", "0")
            except Exception:
                change_24h = 0
                volume = "0"
                high = "0"
                low = "0"

            result = {
                "exchange": "Binance",
                "symbol": symbol,
                "price": price,
                "24h_change_percent": change_24h,
                "24h_high": high,
                "24h_low": low,
                "volume": volume,
                "timestamp": datetime.now().isoformat(),
                "source": "live",
            }
            self.last_prices[symbol] = result
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            self.price_history[symbol].append({"time": time.time(), "price": price})
            return result
        except Exception as e:
            return {
                "exchange": "Binance",
                "symbol": symbol,
                "error": str(e),
                "source": "live",
                "hint": "Network blocked or symbol invalid. Check internet / try BTCUSDT.",
            }

    async def _get_market_data(self, task: Dict) -> Dict:
        symbol = task.get("symbol", "BTCUSDT").upper()
        interval = task.get("interval", "1h")
        limit = task.get("limit", 100)
        try:
            data = self._public_request(
                "/api/v3/klines",
                {"symbol": symbol, "interval": interval, "limit": limit},
            )
            candles = []
            for k in data:
                candles.append({
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return {"symbol": symbol, "interval": interval, "candles": candles, "count": len(candles)}
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    async def _place_order(self, task: Dict) -> Dict:
        if self.test_mode:
            symbol = task.get("symbol", "BTCUSDT").upper()
            side = task.get("side", "BUY").upper()
            qty = task.get("quantity", 0)
            current = self.last_prices.get(symbol, {}).get("price", 0)
            order = {
                "order_id": f"paper_{int(time.time())}",
                "symbol": symbol,
                "side": side,
                "quantity": qty,
                "price": current,
                "total_value": current * qty,
                "mode": "PAPER TRADING (no real money)",
                "status": "filled",
                "timestamp": datetime.now().isoformat(),
            }
            self.open_orders.append(order)
            return order

        if not self.api_key or not self.api_secret:
            return {"error": "Real trading needs API key + secret in config/.env"}

        symbol = task.get("symbol", "BTCUSDT").upper()
        side = task.get("side", "BUY").upper()
        qty = task.get("quantity", 0)
        order_type = task.get("type", "MARKET").upper()
        try:
            result = self._signed_request("POST", "/api/v3/order", {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "quantity": qty,
            })
            result["mode"] = "REAL TRADING"
            result["timestamp"] = datetime.now().isoformat()
            self.open_orders.append(result)
            return result
        except Exception as e:
            return {"error": f"Order failed: {e}", "mode": "REAL TRADING"}

    async def _get_account_info(self, task: Dict) -> Dict:
        if not self.api_key or not self.api_secret:
            return {"error": "API key/secret not configured", "balances": []}
        try:
            result = self._signed_request("GET", "/api/v3/account")
            balances = [
                {
                    "asset": b["asset"],
                    "free": float(b["free"]),
                    "locked": float(b["locked"]),
                }
                for b in result.get("balances", [])
                if float(b["free"]) > 0 or float(b["locked"]) > 0
            ]
            return {
                "can_trade": result.get("canTrade"),
                "balances": balances,
                "note": "Real account data",
            }
        except Exception as e:
            return {"error": f"Account info failed: {e}"}

    async def _check_dse(self, task: Dict) -> Dict:
        from tools.dse_scraper import fetch_dse_market_summary

        ticker = task.get("ticker", "").upper()
        summary = fetch_dse_market_summary()
        if "error" in summary:
            return {
                "exchange": "Dhaka Stock Exchange",
                "error": summary["error"],
                "note": "Direct DSE access may be blocked from some networks",
            }
        rows = summary.get("rows", [])
        if ticker:
            matches = [r for r in rows if r["ticker"].upper() == ticker]
            if matches:
                return {"exchange": "Dhaka Stock Exchange", "ticker": ticker, **matches[0]}
            return {"exchange": "Dhaka Stock Exchange", "ticker": ticker, "error": "Ticker not found"}
        return {
            "exchange": "Dhaka Stock Exchange",
            "total_scripts": len(rows),
            "sample": rows[:5],
            "scraped_at": summary.get("scraped_at"),
        }

    async def _add_to_watchlist(self, task: Dict) -> Dict:
        item = {
            "symbol": task.get("symbol", "").upper(),
            "exchange": task.get("exchange", ""),
            "current_price": task.get("current_price", 0),
            "target_price": task.get("target_price", 0),
            "stop_loss": task.get("stop_loss", 0),
            "notes": task.get("notes", ""),
            "added_at": datetime.now().isoformat(),
        }
        self.watchlist.append(item)
        return item

    async def _get_portfolio_status(self, task: Dict) -> Dict:
        return {
            "total_items": len(self.watchlist),
            "watchlist": self.watchlist,
            "open_orders": self.open_orders,
            "note": "Add real holdings data",
        }

    async def _set_price_alert(self, task: Dict) -> Dict:
        return {
            "alert_id": f"alert_{int(time.time())}",
            "symbol": task.get("symbol", "").upper(),
            "condition": task.get("condition", "above"),
            "target_price": task.get("target_price", 0),
            "status": "active",
        }

    async def _analyze_trend(self, task: Dict) -> Dict:
        symbol = task.get("symbol", "BTCUSDT").upper()
        interval = task.get("interval", "1h")
        try:
            candles = await self._get_market_data({"symbol": symbol, "interval": interval, "limit": 20})
            closes = [c["close"] for c in candles.get("candles", [])]
            if not closes:
                return {"symbol": symbol, "error": "No data"}
            sma5 = sum(closes[-5:]) / min(5, len(closes))
            sma20 = sum(closes[-20:]) / min(20, len(closes))
            trend = "bullish" if sma5 > sma20 else "bearish"
            support = min(closes[-20:])
            resistance = max(closes[-20:])
            return {
                "symbol": symbol,
                "interval": interval,
                "trend": trend,
                "sma5": round(sma5, 2),
                "sma20": round(sma20, 2),
                "support": support,
                "resistance": resistance,
                "last_price": closes[-1],
            }
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

    async def _set_test_mode(self, task: Dict) -> Dict:
        mode = task.get("test_mode", True)
        self.test_mode = bool(mode)
        return {
            "test_mode": self.test_mode,
            "message": "PAPER trading MODE ON - no real money moved" if self.test_mode
            else "REAL trading MODE ON - real money can move!",
        }