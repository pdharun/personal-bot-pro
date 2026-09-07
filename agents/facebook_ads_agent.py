import logging
from typing import Any, Dict, List, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v18.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class FacebookAdsAgent(BaseAgent):
    def __init__(self, config=None):
        super().__init__("FacebookAds", config)
        self.token = (config.facebook.access_token if config else "") or ""
        self.ad_account = (config.facebook.ad_account_id if config else "") or ""
        self.campaigns: Dict[str, Dict] = {}
        self.budget_rules = {
            "min_budget": 5.0,
            "max_budget": 500.0,
            "scale_threshold_roas": 2.0,
            "pause_threshold_roas": 0.5,
        }

    def _api(self, path: str, method: str = "GET", params: Dict = None) -> Dict:
        url = f"{GRAPH_BASE}/{path}"
        params = dict(params or {})
        params["access_token"] = self.token
        try:
            resp = requests.request(method, url, params=params, timeout=15,
                                    verify=False, allow_redirects=True)
        except Exception as e:
            msg = str(e).replace(self.token, "***") if self.token else str(e)
            return {"error": msg, "code": -1}
        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type:
            return {"error": "API unavailable (network blocked).", "code": resp.status_code}
        try:
            data = resp.json()
        except Exception:
            return {"error": "Invalid API response.", "code": resp.status_code}
        if resp.status_code >= 400:
            err = data.get("error", {})
            return {"error": err.get("message", "Unknown error"), "code": err.get("code")}
        return data

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        action = task.get("type")
        handlers = {
            "create_campaign": self._create_campaign,
            "create_ad_set": self._create_ad_set,
            "create_ad": self._create_ad,
            "pause_campaign": self._pause_campaign,
            "resume_campaign": self._resume_campaign,
            "scale_campaign": self._scale_campaign,
            "get_insights": self._get_insights,
            "list_campaigns": self._list_campaigns,
            "get_campaign": self._get_campaign,
            "delete_campaign": self._delete_campaign,
        }
        handler = handlers.get(action)
        if handler:
            return await handler(task)
        return {"error": f"Unknown action: {action}"}

    async def analyze(self, data: Any) -> Dict[str, Any]:
        analysis = {
            "campaigns_to_scale": [],
            "campaigns_to_pause": [],
            "budget_recommendations": [],
        }
        if isinstance(data, list):
            for campaign in data:
                roas = campaign.get("roas", 0)
                spend = campaign.get("spend", 0)
                if roas >= self.budget_rules["scale_threshold_roas"]:
                    analysis["campaigns_to_scale"].append({
                        "id": campaign["id"],
                        "name": campaign["name"],
                        "roas": roas,
                    })
                elif roas <= self.budget_rules["pause_threshold_roas"]:
                    analysis["campaigns_to_pause"].append({
                        "id": campaign["id"],
                        "name": campaign["name"],
                        "roas": roas,
                    })
        return analysis

    async def _list_campaigns(self, task: Dict) -> Dict:
        fields = "id,name,status,objective,daily_budget,lifetime_budget,start_time,end_time"
        data = self._api(f"{self.ad_account}/campaigns", params={"fields": fields})
        if "error" in data:
            return data
        campaigns = data.get("data", [])
        self.campaigns = {c["id"]: c for c in campaigns}
        return {"count": len(campaigns), "campaigns": campaigns}

    async def _get_campaign(self, task: Dict) -> Dict:
        cid = task.get("campaign_id")
        if not cid:
            return {"error": "campaign_id required"}
        fields = "id,name,status,objective,daily_budget,lifetime_budget,start_time,end_time"
        data = self._api(f"{cid}", params={"fields": fields})
        return data

    async def _create_campaign(self, task: Dict) -> Dict:
        if not self.ad_account:
            return {"error": "ad_account not configured in .env"}
        payload = {
            "name": task.get("name", "New Campaign"),
            "objective": task.get("objective", "OUTCOME_SALES"),
            "status": task.get("status", "PAUSED"),
            "special_ad_categories": task.get("special_ad_categories", []),
        }
        daily_budget = task.get("daily_budget")
        if daily_budget:
            payload["daily_budget"] = int(float(daily_budget) * 100)
        data = self._api(f"{self.ad_account}/campaigns", method="POST", params=payload)
        if "error" in data:
            return data
        return {"campaign_id": data.get("id"), "name": payload["name"]}

    async def _create_ad_set(self, task: Dict) -> Dict:
        cid = task.get("campaign_id")
        if not cid:
            return {"error": "campaign_id required"}
        targeting = task.get("targeting", {})
        payload = {
            "name": task.get("name", "New Ad Set"),
            "campaign_id": cid,
            "billing_event": task.get("billing_event", "IMPRESSIONS"),
            "optimization_goal": task.get("optimization_goal", "REACH"),
            "bid_strategy": task.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
            "targeting": {
                "geo_locations": {"countries": ["BD"]},
                **targeting,
            },
            "status": task.get("status", "PAUSED"),
        }
        daily_budget = task.get("daily_budget")
        if daily_budget:
            payload["daily_budget"] = int(float(daily_budget) * 100)
        elif task.get("lifetime_budget"):
            payload["lifetime_budget"] = int(float(task["lifetime_budget"]) * 100)
        data = self._api(f"{self.ad_account}/adsets", method="POST", params=payload)
        if "error" in data:
            return data
        return {"ad_set_id": data.get("id"), "name": payload["name"]}

    async def _create_ad(self, task: Dict) -> Dict:
        adset_id = task.get("ad_set_id")
        page_id = task.get("page_id") or (self.config.facebook.page_id if self.config else "")
        if not adset_id:
            return {"error": "ad_set_id required"}
        creative = task.get("creative") or {}
        if not creative.get("link"):
            return {"error": "creative.link required (or use image/video)"}

        creative_payload = {
            "name": task.get("name", "New Ad Creative"),
            "object_story_spec": {
                "page_id": page_id,
                "link_data": {
                    "link": creative["link"],
                    "message": creative.get("message", "Check this out!"),
                    "name": creative.get("headline", ""),
                    "description": creative.get("description", ""),
                },
            },
        }
        creative_result = self._api(
            f"{self.ad_account}/adcreatives", method="POST", params=creative_payload
        )
        if "error" in creative_result:
            return creative_result

        ad_payload = {
            "name": task.get("name", "New Ad"),
            "adset_id": adset_id,
            "creative": {"creative_id": creative_result.get("id")},
            "status": task.get("status", "PAUSED"),
        }
        ad_result = self._api(f"{self.ad_account}/ads", method="POST", params=ad_payload)
        if "error" in ad_result:
            return ad_result
        return {"ad_id": ad_result.get("id"), "creative_id": creative_result.get("id")}

    async def _pause_campaign(self, task: Dict) -> Dict:
        cid = task.get("campaign_id")
        if not cid:
            return {"error": "campaign_id required"}
        data = self._api(f"{cid}", method="POST", params={"status": "PAUSED"})
        if "error" in data:
            return data
        return {"campaign_id": cid, "status": "PAUSED", "success": True}

    async def _resume_campaign(self, task: Dict) -> Dict:
        cid = task.get("campaign_id")
        if not cid:
            return {"error": "campaign_id required"}
        data = self._api(f"{cid}", method="POST", params={"status": "ACTIVE"})
        if "error" in data:
            return data
        return {"campaign_id": cid, "status": "ACTIVE", "success": True}

    async def _scale_campaign(self, task: Dict) -> Dict:
        cid = task.get("campaign_id")
        factor = task.get("scale_factor", 1.2)
        if not cid:
            return {"error": "campaign_id required"}
        current = self._api(f"{cid}", params={"fields": "daily_budget,name"})
        if "error" in current:
            return current
        old_budget_usd = float(current.get("daily_budget") or 0) / 100
        new_budget_usd = min(old_budget_usd * factor, self.budget_rules["max_budget"])
        data = self._api(f"{cid}", method="POST", params={"daily_budget": int(new_budget_usd * 100)})
        if "error" in data:
            return data
        return {
            "campaign_id": cid,
            "name": current.get("name"),
            "old_budget_usd": old_budget_usd,
            "new_budget_usd": new_budget_usd,
            "scale_factor": factor,
        }

    async def _delete_campaign(self, task: Dict) -> Dict:
        cid = task.get("campaign_id")
        if not cid:
            return {"error": "campaign_id required"}
        data = self._api(f"{cid}", method="DELETE")
        if "error" in data:
            return data
        return {"campaign_id": cid, "deleted": True}

    async def _get_insights(self, task: Dict) -> Dict:
        cid = task.get("campaign_id") or self.ad_account
        level = "campaign" if task.get("campaign_id") else "account"
        fields = "campaign_id,campaign_name,spend,impressions,clicks,ctr,cpc,cpm,reach,purchase_roas,actions"
        params = {
            "fields": fields,
            "level": level,
            "date_preset": task.get("date_preset", "last_7d"),
            "limit": task.get("limit", 10),
        }
        data = self._api(f"{cid}/insights", params=params)
        if "error" in data:
            return data
        rows = data.get("data", [])
        for r in rows:
            roas = 0.0
            for a in r.get("actions", []):
                if a.get("action_type") == "purchase":
                    roas = float(a.get("value", 0))
            spend = float(r.get("spend", 0))
            if spend > 0:
                r["roas"] = round(roas / spend, 2)
            else:
                r["roas"] = 0.0
        return {"count": len(rows), "insights": rows, "ad_account": self.ad_account}