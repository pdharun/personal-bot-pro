import logging
from typing import Any, Dict, List
from datetime import datetime
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class AlgorithmAgent(BaseAgent):
    def __init__(self, config=None):
        super().__init__("Algorithm", config)
        self.metrics_history: List[Dict] = []
        self.alerts: List[Dict] = []

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("type")
        handlers = {
            "analyze_performance": self._analyze_performance,
            "detect_anomalies": self._detect_anomalies,
            "recommend_optimization": self._recommend_optimization,
            "track_algorithm_changes": self._track_algorithm_changes,
        }
        handler = handlers.get(action)
        if handler:
            return await handler(task)
        return {"error": f"Unknown action: {action}"}

    async def analyze(self, data: Any) -> Dict[str, Any]:
        return {
            "algorithm_health": "monitoring_active",
            "key_signals": [
                "engagement_rate_trend",
                "reach_decay_rate",
                "click_through_rate",
            ],
            "status": "All systems normal",
        }

    async def _analyze_performance(self, task: Dict) -> Dict:
        metrics = {
            "engagement_rate": task.get("engagement_rate", 0),
            "reach": task.get("reach", 0),
            "impressions": task.get("impressions", 0),
            "ctr": task.get("ctr", 0),
            "cpm": task.get("cpm", 0),
        }
        self.metrics_history.append({
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
        })
        score = self._calculate_health_score(metrics)
        return {
            "metrics": metrics,
            "health_score": score,
            "status": "healthy" if score > 60 else "needs_attention",
        }

    async def _detect_anomalies(self, task: Dict) -> Dict:
        anomalies = []
        if len(self.metrics_history) >= 2:
            prev = self.metrics_history[-2]["metrics"]
            curr = self.metrics_history[-1]["metrics"]
            if prev.get("engagement_rate", 0) > 0:
                change = ((curr.get("engagement_rate", 0) - prev["engagement_rate"])
                          / prev["engagement_rate"] * 100)
                if abs(change) > 20:
                    anomalies.append({
                        "type": "engagement_shift",
                        "change_percent": change,
                        "severity": "high" if abs(change) > 50 else "medium",
                    })
        return {"anomalies": anomalies, "checked_at": datetime.now().isoformat()}

    async def _recommend_optimization(self, task: Dict) -> Dict:
        return {
            "recommendations": [
                "Optimize posting schedule based on audience activity",
                "A/B test ad creatives weekly",
                "Refresh audience targeting every 14 days",
                "Monitor frequency - keep under 3.0",
                "Scale budgets gradually (20% max per adjustment)",
            ],
            "priority_actions": [
                "Review underperforming ad sets",
                "Update creative assets",
                "Adjust bid strategy if CPM is rising",
            ],
        }

    async def _track_algorithm_changes(self, task: Dict) -> Dict:
        return {
            "recent_changes": [
                "Video content prioritized in feed",
                "Authenticity signals weighted higher",
                "Reels getting organic boost",
            ],
            "impact_on_ads": "Minimal - focus on quality content",
        }

    def _calculate_health_score(self, metrics: Dict) -> float:
        score = 50.0
        er = metrics.get("engagement_rate", 0)
        if er > 3:
            score += 20
        elif er > 1:
            score += 10
        elif er < 0.5:
            score -= 20
        ctr = metrics.get("ctr", 0)
        if ctr > 2:
            score += 15
        elif ctr > 1:
            score += 5
        impressions = metrics.get("impressions", 0)
        if impressions > 10000:
            score += 15
        return min(max(score, 0), 100)
