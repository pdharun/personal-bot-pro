import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, name: str, config: Any = None):
        self.name = name
        self.config = config
        self.is_running = False
        self.last_action_time: Optional[datetime] = None
        self.logger = logging.getLogger(f"agent.{name}")

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def analyze(self, data: Any) -> Dict[str, Any]:
        pass

    async def start(self):
        self.is_running = True
        self.logger.info(f"{self.name} agent started")

    async def stop(self):
        self.is_running = False
        self.logger.info(f"{self.name} agent stopped")

    def log_action(self, action: str, details: Any = None):
        self.last_action_time = datetime.now()
        self.logger.info(f"Action: {action} | Details: {details}")

    async def safe_execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = await self.execute(task)
            self.log_action(task.get("type", "unknown"), result)
            return {"success": True, "data": result}
        except Exception as e:
            self.logger.error(f"Error in {self.name}: {e}")
            return {"success": False, "error": str(e)}
