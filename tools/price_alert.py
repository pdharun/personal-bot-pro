import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PriceAlertEngine:
    def __init__(self, market_agent):
        self.market_agent = market_agent
        self.alerts: List[Dict] = []
        self.triggered_alerts: List[Dict] = []

    def add_alert(self, symbol: str, condition: str, target_price: float, note: str = "") -> Dict:
        alert = {
            "alert_id": f"alert_{int(time.time() * 1000)}",
            "symbol": symbol.upper(),
            "condition": condition,
            "target_price": float(target_price),
            "note": note,
            "active": True,
            "created_at": time.time(),
        }
        self.alerts.append(alert)
        return alert

    def remove_alert(self, alert_id: str) -> bool:
        for a in self.alerts:
            if a["alert_id"] == alert_id:
                a["active"] = False
                return True
        return False

    def list_alerts(self) -> List[Dict]:
        return [a for a in self.alerts if a["active"]]

    def disable_all(self):
        for a in self.alerts:
            a["active"] = False

    async def check_all(self) -> List[Dict]:
        triggered = []
        active_alerts = self.list_alerts()
        symbols = list({a["symbol"] for a in active_alerts})
        prices = {}
        for symbol in symbols:
            result = await self.market_agent.execute({"type": "check_binance", "symbol": symbol})
            if "price" in result:
                prices[symbol] = result["price"]

        for alert in active_alerts:
            price = prices.get(alert["symbol"])
            if price is None:
                continue
            hit = False
            if alert["condition"] == "above" and price >= alert["target_price"]:
                hit = True
            elif alert["condition"] == "below" and price <= alert["target_price"]:
                hit = True
            if hit:
                triggered.append({
                    "alert_id": alert["alert_id"],
                    "symbol": alert["symbol"],
                    "condition": alert["condition"],
                    "target_price": alert["target_price"],
                    "current_price": price,
                    "note": alert["note"],
                    "triggered_at": int(time.time()),
                })
                alert["active"] = False
                self.triggered_alerts.append(triggered[-1])
        return triggered

    def get_status(self) -> Dict:
        return {
            "active_alerts": len(self.list_alerts()),
            "total_created": len(self.alerts),
            "triggered_count": len(self.triggered_alerts),
            "recent_triggered": self.triggered_alerts[-5:],
        }