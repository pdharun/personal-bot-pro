import asyncio
import logging
from typing import Any, Dict, List
from datetime import datetime
from .base_agent import BaseAgent
from .facebook_ads_agent import FacebookAdsAgent
from .facebook_post_agent import FacebookPostAgent
from .algorithm_agent import AlgorithmAgent
from .whatsapp_agent import WhatsAppAgent
from .market_agent import MarketAgent

logger = logging.getLogger(__name__)


class Orchestrator(BaseAgent):
    def __init__(self, config=None):
        super().__init__("Orchestrator", config)
        self.agents = {
            "facebook_ads": FacebookAdsAgent(config),
            "facebook_post": FacebookPostAgent(config),
            "algorithm": AlgorithmAgent(config),
            "whatsapp": WhatsAppAgent(config),
            "market": MarketAgent(config),
        }
        self.task_queue: List[Dict] = []
        self.completed_tasks: List[Dict] = []

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = task.get("agent")
        if agent_name and agent_name in self.agents:
            agent = self.agents[agent_name]
            return await agent.safe_execute(task)
        return await self._route_task(task)

    async def analyze(self, data: Any) -> Dict[str, Any]:
        results = {}
        for name, agent in self.agents.items():
            results[name] = await agent.analyze(data)
        return results

    async def _route_task(self, task: Dict) -> Dict:
        task_type = task.get("type", "")
        agent_map = {
            "create_campaign": "facebook_ads",
            "create_ad_set": "facebook_ads",
            "create_ad": "facebook_ads",
            "list_campaigns": "facebook_ads",
            "get_campaign": "facebook_ads",
            "pause_campaign": "facebook_ads",
            "resume_campaign": "facebook_ads",
            "scale_campaign": "facebook_ads",
            "get_insights": "facebook_ads",
            "delete_campaign": "facebook_ads",
            "create_post": "facebook_post",
            "schedule_post": "facebook_post",
            "generate_content": "facebook_post",
            "analyze_performance": "algorithm",
            "detect_anomalies": "algorithm",
            "recommend_optimization": "algorithm",
            "send_whatsapp": "whatsapp",
            "send_template": "whatsapp",
            "check_binance": "market",
            "check_dse": "market",
            "analyze_trend": "market",
        }
        agent_name = agent_map.get(task_type)
        if agent_name:
            return await self.agents[agent_name].safe_execute(task)
        return {"error": f"No agent found for task: {task_type}"}

    async def run_cycle(self):
        self.logger.info("Starting orchestrator cycle")
        market_data = await self.agents["market"].execute({"type": "check_binance"})
        algo_analysis = await self.agents["algorithm"].execute({
            "type": "analyze_performance",
            "engagement_rate": 2.5,
            "reach": 5000,
            "impressions": 15000,
            "ctr": 1.8,
        })
        return {
            "cycle_time": datetime.now().isoformat(),
            "market": market_data,
            "algorithm": algo_analysis,
        }

    async def process_user_command(self, command: str) -> str:
        command_lower = command.lower()
        if "campaign" in command_lower and "list" in command_lower:
            result = await self.agents["facebook_ads"].safe_execute({"type": "list_campaigns"})
            return f"Campaigns: {result}"
        elif "insight" in command_lower:
            result = await self.agents["facebook_ads"].safe_execute({"type": "get_insights"})
            return f"Insights: {result}"
        elif "facebook" in command_lower and "campaign" in command_lower and "pause" in command_lower:
            cid = self._extract_id(command)
            result = await self.agents["facebook_ads"].safe_execute({"type": "pause_campaign", "campaign_id": cid})
            return f"Pause: {result}"
        elif "facebook" in command_lower and "campaign" in command_lower and "resume" in command_lower:
            cid = self._extract_id(command)
            result = await self.agents["facebook_ads"].safe_execute({"type": "resume_campaign", "campaign_id": cid})
            return f"Resume: {result}"
        elif "facebook" in command_lower and "campaign" in command_lower:
            result = await self.agents["facebook_ads"].safe_execute({
                "type": "create_campaign",
                "name": command,
            })
            return f"Campaign created: {result}"
        elif "post" in command_lower:
            result = await self.agents["facebook_post"].safe_execute({
                "type": "create_post",
                "message": command,
            })
            return f"Post created: {result}"
        elif "whatsapp" in command_lower or "wa" in command_lower:
            result = await self.agents["whatsapp"].safe_execute({
                "type": "send_message",
                "message": command,
            })
            return f"WhatsApp: {result}"
        elif "binance" in command_lower or "crypto" in command_lower:
            result = await self.agents["market"].execute({
                "type": "check_binance",
                "symbol": "BTCUSDT",
            })
            return f"Market: {result}"
        elif "dse" in command_lower or "stock" in command_lower:
            result = await self.agents["market"].execute({
                "type": "check_dse",
            })
            return f"DSE: {result}"
        else:
            return await self._general_response(command)

    def _extract_id(self, command: str) -> str:
        import re
        match = re.search(r"(\d{10,})", command)
        return match.group(1) if match else ""

    async def _general_response(self, command: str) -> str:
        return (
            f"I received your command: '{command}'\n"
            "Available commands:\n"
            "- Create Facebook campaign [name]\n"
            "- Create post [message]\n"
            "- Send WhatsApp [message]\n"
            "- Check Binance [symbol]\n"
            "- Check DSE\n"
            "- Analyze performance"
        )

    async def start(self):
        await super().start()
        for name, agent in self.agents.items():
            await agent.start()
        self.logger.info("All agents started")

    async def stop(self):
        await super().stop()
        for name, agent in self.agents.items():
            await agent.stop()
        self.logger.info("All agents stopped")
