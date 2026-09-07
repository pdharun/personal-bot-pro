import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TradingStrategy:
    name = "base"

    async def generate_signals(self, market_agent, symbol: str) -> Dict[str, Any]:
        raise NotImplementedError


class SMACrossStrategy(TradingStrategy):
    name = "sma_cross"

    def __init__(self):
        self.fast_period = 5
        self.slow_period = 20
        self.interval = "5m"

    async def generate_signals(self, market_agent, symbol: str) -> Dict[str, Any]:
        data = await market_agent.execute({
            "type": "get_market_data",
            "symbol": symbol,
            "interval": self.interval,
            "limit": 50,
        })
        candles = data.get("candles", [])
        if len(candles) < 20:
            return {"symbol": symbol, "error": "Not enough data", "signal": "HOLD"}
        closes = [c["close"] for c in candles]
        fast_sma = sum(closes[-self.fast_period:]) / self.fast_period
        slow_sma = sum(closes[-self.slow_period:]) / self.slow_period
        prev_fast = sum(closes[-self.fast_period - 1:-1]) / self.fast_period
        prev_slow = sum(closes[-self.slow_period - 1:-1]) / self.slow_period

        signal = "HOLD"
        reason = "No crossover detected"
        if prev_fast <= prev_slow and fast_sma > slow_sma:
            signal = "BUY"
            reason = f"Bullish crossover (Fast {round(fast_sma,2)} > Slow {round(slow_sma,2)})"
        elif prev_fast >= prev_slow and fast_sma < slow_sma:
            signal = "SELL"
            reason = f"Bearish crossover (Fast {round(fast_sma,2)} < Slow {round(slow_sma,2)})"

        return {
            "strategy": self.name,
            "symbol": symbol,
            "interval": self.interval,
            "signal": signal,
            "reason": reason,
            "fast_sma": round(fast_sma, 2),
            "slow_sma": round(slow_sma, 2),
            "last_price": closes[-1],
        }


class RSIMeanReversionStrategy(TradingStrategy):
    name = "rsi_mean_reversion"

    def __init__(self):
        self.interval = "5m"
        self.oversold = 30
        self.overbought = 70

    async def generate_signals(self, market_agent, symbol: str) -> Dict[str, Any]:
        data = await market_agent.execute({
            "type": "get_market_data",
            "symbol": symbol,
            "interval": self.interval,
            "limit": 30,
        })
        candles = data.get("candles", [])
        if len(candles) < 15:
            return {"symbol": symbol, "error": "Not enough data", "signal": "HOLD"}
        rsi = self._calculate_rsi([c["close"] for c in candles], period=14)

        signal = "HOLD"
        reason = "RSI in neutral zone"
        if rsi <= self.oversold:
            signal = "BUY"
            reason = f"RSI oversold ({round(rsi,2)} <= {self.oversold})"
        elif rsi >= self.overbought:
            signal = "SELL"
            reason = f"RSI overbought ({round(rsi,2)} >= {self.overbought})"

        return {
            "strategy": self.name,
            "symbol": symbol,
            "interval": self.interval,
            "signal": signal,
            "reason": reason,
            "rsi": round(rsi, 2),
            "last_price": candles[-1]["close"],
        }

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[1 - period:]) / period
        avg_loss = sum(losses[1 - period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


class AutoTrader:
    def __init__(self, market_agent):
        self.market_agent = market_agent
        self.strategies: Dict[str, TradingStrategy] = {}
        self.risk_params = {
            "default_quantity": 0.0001,
            "max_loss_percent": 10.0,
            "test_mode": True,
        }
        self.trade_log: List[Dict] = []
        self._register_defaults()

    def _register_defaults(self):
        self.register_strategy(SMACrossStrategy())
        self.register_strategy(RSIMeanReversionStrategy())

    def register_strategy(self, strategy: TradingStrategy):
        self.strategies[strategy.name] = strategy

    def set_risk_params(self, **kwargs):
        self.risk_params.update(kwargs)
        return self.risk_params

    async def run_once(self, symbol: str, strategy_name: str = "sma_cross") -> Dict[str, Any]:
        strategy = self.strategies.get(strategy_name)
        if not strategy:
            return {"error": f"Unknown strategy: {strategy_name}",
                    "available": list(self.strategies.keys())}

        signal_result = await strategy.generate_signals(self.market_agent, symbol)
        if signal_result.get("signal") in ("BUY", "SELL"):
            order = await self.market_agent.execute(
                await self._build_order(symbol, signal_result)
            )
            self.trade_log.append(order)
            return {**signal_result, "order": order}
        return signal_result

    async def _build_order(self, symbol: str, signal: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "place_order",
            "symbol": symbol.replace("/", ""),
            "side": signal["signal"],
            "quantity": self.risk_params["default_quantity"],
        }

    def get_status(self) -> Dict:
        return {
            "strategies": list(self.strategies.keys()),
            "risk_params": self.risk_params,
            "total_trades": len(self.trade_log),
            "recent_trades": self.trade_log[-5:],
        }