from typing import Dict, List, Optional


def sma(values: List[float], period: int) -> List[Optional[float]]:
    result = [None] * len(values)
    if len(values) < period or period <= 0:
        return result
    running = sum(values[:period])
    result[period - 1] = running / period
    for i in range(period, len(values)):
        running += values[i] - values[i - period]
        result[i] = running / period
    return result


def ema(values: List[float], period: int) -> List[Optional[float]]:
    result = [None] * len(values)
    if len(values) < period or period <= 0:
        return result
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    for i in range(period, len(values)):
        result[i] = values[i] * k + result[i - 1] * (1 - k)
    return result


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    result = [None] * len(values)
    if len(values) <= period:
        return result
    gains = []
    losses = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = 100.0 if avg_loss == 0 else avg_gain / avg_loss
        result[i + 1] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + rs))
    return result


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line = [None] * len(values)
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]
    cleaned = [m for m in macd_line if m is not None]
    offset = len(macd_line) - len(cleaned)
    sig = [None] * len(macd_line)
    ema_sig = ema(cleaned, signal)
    for i, v in enumerate(ema_sig):
        if v is not None:
            sig[i + offset] = v
    hist = [None] * len(values)
    for i in range(len(values)):
        if macd_line[i] is not None and sig[i] is not None:
            hist[i] = macd_line[i] - sig[i]
    return macd_line, sig, hist


def bollinger(values: List[float], period: int = 20, num_std: float = 2.0):
    mid = sma(values, period)
    upper = [None] * len(values)
    lower = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        mean = mid[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
    return upper, mid, lower


def all_indicators(candles: List[Dict]) -> Dict:
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    indicators = {
        "sma_5": sma(closes, 5),
        "sma_10": sma(closes, 10),
        "sma_20": sma(closes, 20),
        "sma_50": sma(closes, 50),
        "ema_12": ema(closes, 12),
        "ema_26": ema(closes, 26),
        "rsi_14": rsi(closes, 14),
        "bollinger_20": bollinger(closes, 20, 2.0),
    }
    indicators["macd"] = macd(closes)
    indicators["vwap"] = _vwap(highs, lows, closes, volumes)
    return indicators


def _vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float]) -> List[Optional[float]]:
    result = [None] * len(closes)
    cum_vp = 0.0
    cum_v = 0.0
    for i in range(len(closes)):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        cum_vp += tp * volumes[i]
        cum_v += volumes[i]
        result[i] = cum_vp / cum_v if cum_v else None
    return result


def signal_summary(indicators: Dict, candle: Dict) -> Dict[str, str]:
    rsi_vals = indicators["rsi_14"]
    r = rsi_vals[-1]
    boll = indicators["bollinger_20"]
    upper, mid, lower = boll
    close = candle["close"]
    signals = []

    if r is not None:
        if r <= 30:
            signals.append("RSI oversold -> BUY zone")
        elif r >= 70:
            signals.append("RSI overbought -> SELL zone")
        else:
            signals.append(f"RSI neutral ({round(r, 1)})")

    if mid[-1] is not None and lower[-1] is not None and upper[-1] is not None:
        if close <= lower[-1]:
            signals.append("Price at lower Bollinger -> oversold")
        elif close >= upper[-1]:
            signals.append("Price at upper Bollinger -> overbought")

    macd_line, sig, hist = indicators["macd"]
    if macd_line[-1] is not None and sig[-1] is not None:
        if macd_line[-1] > sig[-1]:
            signals.append("MACD bullish (above signal)")
        else:
            signals.append("MACD bearish (below signal)")

    sma5 = indicators["sma_5"]
    sma20 = indicators["sma_20"]
    if sma5[-1] is not None and sma20[-1] is not None:
        if sma5[-1] > sma20[-1]:
            signals.append("Short-term UPTREND")
        else:
            signals.append("Short-term DOWNTREND")

    verdict = "BUY" if "BUY zone" in signals or "oversold" in str(signals).lower() and "MACD bullish" in str(signals) else "SELL" if "SELL zone" in signals else "HOLD"
    return {"signals": signals, "verdict": verdict}