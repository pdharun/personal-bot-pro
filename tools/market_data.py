import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://data-api.binance.vision",
]
COINBASE = "https://api.coinbase.com"

# Map common Binance-style symbols (BTCUSDT) to Coinbase pairs (BTC-USD)
_SYMBOL_MAP = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "BNB": "BNB-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "ADA": "ADA-USD",
    "DOGE": "DOGE-USD",
    "AVAX": "AVAX-USD",
    "LINK": "LINK-USD",
    "DOT": "DOT-USD",
    "MATIC": "MATIC-USD",
    "LTC": "LTC-USD",
    "SHIB": "SHIB-USD",
    "TRX": "TRX-USD",
    "UNI": "UNI-USD",
    "ATOM": "ATOM-USD",
    "ETC": "ETC-USD",
    "XLM": "XLM-USD",
    "BCH": "BCH-USD",
    "NEAR": "NEAR-USD",
    "APT": "APT-USD",
    "FIL": "FIL-USD",
    "ARB": "ARB-USD",
    "OP": "OP-USD",
    "SUI": "SUI-USD",
    "INJ": "INJ-USD",
    "SEI": "SEI-USD",
    "TIA": "TIA-USD",
    "PEPE": "PEPE-USD",
    "WIF": "WIF-USD",
    "BONK": "BONK-USD",
    "FLOKI": "FLOKI-USD",
    "TON": "TON-USD",
    "AAVE": "AAVE-USD",
    "MKR": "MKR-USD",
    "CRV": "CRV-USD",
    "SAND": "SAND-USD",
    "MANA": "MANA-USD",
    "AXS": "AXS-USD",
    "GALA": "GALA-USD",
    "CHZ": "CHZ-USD",
    "ENJ": "ENJ-USD",
    "THETA": "THETA-USD",
    "XTZ": "XTZ-USD",
    "ALGO": "ALGO-USD",
    "HBAR": "HBAR-USD",
    "VET": "VET-USD",
    "ICP": "ICP-USD",
    "EGLD": "EGLD-USD",
    "FLOW": "FLOW-USD",
    "MAGIC": "MAGIC-USD",
}

# Symbol -> full name table for display
COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "BNB": "BNB", "SOL": "Solana",
    "XRP": "XRP", "ADA": "Cardano", "DOGE": "Dogecoin", "AVAX": "Avalanche",
    "LINK": "Chainlink", "DOT": "Polkadot", "MATIC": "Polygon", "LTC": "Litecoin",
    "SHIB": "Shiba Inu", "TRX": "Tron", "UNI": "Uniswap", "ATOM": "Cosmos",
    "ETC": "Ethereum Classic", "XLM": "Stellar", "BCH": "Bitcoin Cash",
    "NEAR": "NEAR Protocol", "APT": "Aptos", "FIL": "Filecoin", "ARB": "Arbitrum",
    "OP": "Optimism", "SUI": "Sui", "INJ": "Injective", "SEI": "Sei",
    "TIA": "Celestia", "PEPE": "Pepe", "WIF": "Dogwifhat", "BONK": "Bonk",
    "FLOKI": "Floki", "TON": "Toncoin", "AAVE": "Aave", "MKR": "Maker",
    "CRV": "Curve", "SAND": "The Sandbox", "MANA": "Decentraland",
    "AXS": "Axie Infinity", "GALA": "Gala", "CHZ": "Chiliz", "ENJ": "Enjin",
    "THETA": "Theta", "XTZ": "Tezos", "ALGO": "Algorand", "HBAR": "Hedera",
    "VET": "VeChain", "ICP": "Internet Computer", "EGLD": "MultiversX",
    "FLOW": "Flow", "MAGIC": "Magic",
}

BINANCE_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1d",
}

# Period -> seconds (approximation used to map Binance intervals to Coinbase periods)
COINBASE_PERIOD_SECONDS = {
    "hour": 3600, "day": 86400, "week": 604800,
}

INTERVAL_SUGGESTIONS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400,
}


class MarketDataProvider:
    def __init__(self, binance_key: str = "", binance_secret: str = ""):
        self.binance_key = binance_key
        self.binance_secret = binance_secret
        self.base_base = None

    def _session(self):
        s = requests.Session()
        s.verify = False
        s.trust_env = False
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        return s

    def _binance_get(self, path: str, params: Dict = None, timeout: int = 6) -> Optional[Any]:
        hosts = [BINANCE_HOSTS[0], BINANCE_HOSTS[-1]]
        results = []
        with ThreadPoolExecutor(max_workers=len(hosts)) as pool:
            futures = {pool.submit(self._binance_get_host, h, path, params, timeout): h for h in hosts}
            for f in futures:
                try:
                    data = f.result(timeout=timeout + 2)
                    if data is not None:
                        results.append(data)
                except Exception:
                    pass
        for data in results:
            if isinstance(data, (dict, list)):
                return data
        return None

    def _binance_get_host(self, host: str, path: str, params: Dict = None,
                          timeout: int = 6) -> Optional[Any]:
        try:
            resp = self._session().get(f"{host}{path}", params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def _coinbase_get(self, path: str, timeout: int = 10) -> Optional[Any]:
        try:
            resp = self._session().get(f"{COINBASE}{path}", timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"Coinbase request failed: {e}")
        return None

    def get_price(self, base: str) -> Optional[Dict]:
        base = (base or "").replace("USDT", "").replace("USD", "").upper()
        # Try Binance first
        binance_data = self._binance_get("/api/v3/ticker/price", {"symbol": base + "USDT"})
        if binance_data and "price" in binance_data:
            pair = _SYMBOL_MAP.get(base, f"{base}-USD")
            return {
                "base": base,
                "quote": "USD",
                "price": float(binance_data["price"]),
                "source": "binance",
            }
        # Fallback to Coinbase
        pair = _SYMBOL_MAP.get(base, f"{base}-USD")
        data = self._coinbase_get(f"/v2/prices/{pair}/spot")
        if data:
            amount = data.get("data", {}).get("amount")
            if amount:
                return {
                    "base": base,
                    "quote": "USD",
                    "price": float(amount),
                    "source": "coinbase",
                }
        return None

    def get_all_prices(self) -> List[Dict]:
        # Quick parallel approach: probe Binance briefly while building Coinbase board.
        binance_rows = [None]

        def probe_binance():
            try:
                hosts = [BINANCE_HOSTS[0], BINANCE_HOSTS[-1]]
                tickers = None
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(self._binance_get_host, h, "/api/v3/ticker/24hr",
                                           None, 3) for h in hosts]
                    for f in futures:
                        try:
                            data = f.result(timeout=5)
                        except Exception:
                            data = None
                        if isinstance(data, list) and data:
                            tickers = data
                            break
                if not isinstance(tickers, list) or not tickers:
                    return
                rows = []
                for t in tickers:
                    sym = t.get("symbol", "")
                    if sym.endswith("USDT"):
                        base = sym[:-4]
                        rows.append({
                            "symbol": base,
                            "name": COIN_NAMES.get(base, base),
                            "price": float(t.get("lastPrice", 0) or 0),
                            "change_24h": float(t.get("priceChangePercent", 0) or 0),
                            "high_24h": float(t.get("highPrice", 0) or 0),
                            "low_24h": float(t.get("lowPrice", 0) or 0),
                            "volume": float(t.get("volume", 0) or 0),
                            "quote_volume": float(t.get("quoteVolume", 0) or 0),
                            "source": "binance",
                        })
                rows.sort(key=lambda r: -r["quote_volume"])
                binance_rows[0] = rows
            except Exception:
                pass

        probe = threading.Thread(target=probe_binance, daemon=True)
        probe.start()

        symbols = list(_SYMBOL_MAP.keys())

        def fetch(base: str) -> Optional[Dict]:
            pair = _SYMBOL_MAP.get(base, f"{base}-USD")
            try:
                data = self._coinbase_get(f"/v2/prices/{pair}/historic?period=day", timeout=12)
                if not data:
                    return None
                series = data.get("data", {}).get("prices") or []
                if not series:
                    return None
                newest_first = int(series[0]["time"]) >= int(series[-1]["time"])
                ordered = series if newest_first else list(reversed(series))
                cur = float(ordered[0]["price"])
                old = float(ordered[-1]["price"])
                percents = [
                    float(p["price"])
                    for p in ordered
                    if p.get("price")
                ]
                chg = ((cur - old) / old * 100.0) if old else 0.0
                return {
                    "symbol": base,
                    "name": COIN_NAMES.get(base, base),
                    "price": cur,
                    "change_24h": round(chg, 2),
                    "high_24h": round(max(percents), 2),
                    "low_24h": round(min(percents), 2),
                    "volume": 0.0,
                    "quote_volume": 0.0,
                    "source": "coinbase",
                }
            except Exception:
                return None

        rows = []
        with ThreadPoolExecutor(max_workers=24) as pool:
            for r in pool.map(fetch, symbols):
                if r:
                    rows.append(r)
        rows.sort(key=lambda r: -r["price"])

        probe.join(timeout=20)
        if binance_rows[0]:
            return binance_rows[0]
        return rows

    def get_klines(self, base: str, interval: str = "1h", limit: int = 100) -> List[Dict]:
        base = (base or "").replace("USDT", "").replace("USD", "").upper()
        # Try Binance klines
        if interval in BINANCE_INTERVAL_MAP:
            data = self._binance_get(
                "/api/v3/klines",
                {"symbol": base + "USDT", "interval": BINANCE_INTERVAL_MAP[interval], "limit": min(limit, 1000)},
                timeout=8,
            )
            if isinstance(data, list) and data:
                candles = []
                for k in data:
                    ts = int(k[0])
                    if ts > 100_000_000_000:
                        ts = ts // 1000
                    candles.append({
                        "time": ts,
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    })
                return candles
        # Fallback: Coinbase historic prices -> resample into OHLC candles
        pair = _SYMBOL_MAP.get(base, f"{base}-USD")
        needed = min(limit, 300)
        candles = self._klines_from_coinbase(pair, interval, needed)
        if candles:
            return candles
        return []

    def _klines_from_coinbase(self, pair: str, interval: str, limit: int) -> List[Dict]:
        step = INTERVAL_SUGGESTIONS.get(interval, 3600)
        series = []
        periods = ["day", "week"] if step >= 900 else ["day"]
        if step >= 86400:
            periods = ["week", "day"]

        def fetch(period: str) -> None:
            try:
                data = self._coinbase_get(f"/v2/prices/{pair}/historic?period={period}", timeout=12)
                if data and data.get("data", {}).get("prices"):
                    series.extend(data["data"]["prices"])
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=len(periods)) as pool:
            list(pool.map(fetch, periods))

        if not series:
            return []
        unique = {}
        for item in series:
            t = int(item.get("time", 0))
            if t not in unique:
                unique[t] = float(item.get("price", 0.0))
        ordered = [(t, unique[t]) for t in sorted(unique)]
        if len(ordered) < 2:
            return []
        t0 = ordered[0][0]
        buckets: Dict[int, List[float]] = {}
        for t, price in ordered:
            bi = int((t - t0) // step)
            buckets.setdefault(bi, []).append(price)
        candles = []
        for bi in sorted(buckets):
            values = buckets[bi]
            if not values:
                continue
            candles.append({
                "time": t0 + bi * step,
                "open": values[0],
                "high": max(values),
                "low": min(values),
                "close": values[-1],
                "volume": 0.0,
            })
        return candles[-limit:]

    def _interval_to_cb_period(self, interval: str) -> str:
        seconds = INTERVAL_SUGGESTIONS.get(interval, 3600)
        if seconds <= 3600:
            return "hour"
        if seconds <= 86400:
            return "day"
        return "week"

    def get_known_symbols(self) -> List[str]:
        return list(_SYMBOL_MAP.keys())


provider = MarketDataProvider()