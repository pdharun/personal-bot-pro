import logging
from typing import Any, Dict, List
from datetime import datetime
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class WhatsAppAgent(BaseAgent):
    def __init__(self, config=None):
        super().__init__("WhatsApp", config)
        self.contacts: List[Dict] = []
        self.campaigns: List[Dict] = []
        self.templates: Dict[str, str] = {
            "welcome": "Welcome to our service! How can we help you?",
            "promo": "Special offer just for you! {offer_details}",
            "followup": "Hi {name}, just checking in. Any questions?",
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("type")
        handlers = {
            "send_message": self._send_message,
            "send_template": self._send_template,
            "create_broadcast": self._create_broadcast,
            "add_contact": self._add_contact,
            "get_conversation": self._get_conversation,
        }
        handler = handlers.get(action)
        if handler:
            return await handler(task)
        return {"error": f"Unknown action: {action}"}

    async def analyze(self, data: Any) -> Dict[str, Any]:
        return {
            "response_rate": "N/A",
            "active_conversations": len(self.contacts),
            "campaign_performance": {
                "sent": sum(c.get("sent", 0) for c in self.campaigns),
                "delivered": sum(c.get("delivered", 0) for c in self.campaigns),
                "read": sum(c.get("read", 0) for c in self.campaigns),
            },
        }

    async def _send_message(self, task: Dict) -> Dict:
        return {
            "message_id": f"wa_msg_{datetime.now().timestamp()}",
            "to": task.get("phone", ""),
            "status": "sent",
            "type": task.get("message_type", "text"),
        }

    async def _send_template(self, task: Dict) -> Dict:
        template_name = task.get("template", "welcome")
        template = self.templates.get(template_name, "")
        params = task.get("params", {})
        for key, value in params.items():
            template = template.replace(f"{{{key}}}", value)
        return {
            "template": template_name,
            "message": template,
            "status": "sent",
        }

    async def _create_broadcast(self, task: Dict) -> Dict:
        broadcast = {
            "broadcast_id": f"bc_{len(self.campaigns) + 1}",
            "name": task.get("name", "Broadcast"),
            "message": task.get("message", ""),
            "contacts": task.get("contacts", []),
            "sent": 0,
            "delivered": 0,
            "read": 0,
            "status": "created",
        }
        self.campaigns.append(broadcast)
        return broadcast

    async def _add_contact(self, task: Dict) -> Dict:
        contact = {
            "phone": task.get("phone", ""),
            "name": task.get("name", ""),
            "tags": task.get("tags", []),
            "added_at": datetime.now().isoformat(),
        }
        self.contacts.append(contact)
        return contact

    async def _get_conversation(self, task: Dict) -> Dict:
        phone = task.get("phone", "")
        return {
            "phone": phone,
            "messages": [],
            "note": "Connect WhatsApp Business API for real data",
        }
