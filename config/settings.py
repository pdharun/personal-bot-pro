import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


def _find_env_file() -> Optional[Path]:
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / ".env")
        candidates.append(exe_dir / "config" / ".env")
    candidates.append(Path(__file__).resolve().parent / ".env")
    candidates.append(Path(os.getcwd()) / ".env")
    candidates.append(Path(os.getcwd()) / "config" / ".env")
    for env_path in candidates:
        if env_path and env_path.exists():
            return env_path
    return None


_ENV_FILE = _find_env_file()
if _ENV_FILE:
    load_dotenv(_ENV_FILE)


@dataclass
class FacebookConfig:
    app_id: str = os.getenv("FB_APP_ID", "")
    app_secret: str = os.getenv("FB_APP_SECRET", "")
    access_token: str = os.getenv("FB_ACCESS_TOKEN", "")
    ad_account_id: str = os.getenv("FB_AD_ACCOUNT_ID", "")
    page_id: str = os.getenv("FB_PAGE_ID", "")


@dataclass
class WhatsAppConfig:
    phone_number_id: str = os.getenv("WA_PHONE_NUMBER_ID", "")
    access_token: str = os.getenv("WA_ACCESS_TOKEN", "")
    api_version: str = "v18.0"


@dataclass
class AIConfig:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = "gpt-4"
    temperature: float = 0.7


@dataclass
class MarketConfig:
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    dse_data_source: str = "https://dsebd.org"


@dataclass
class BotConfig:
    facebook: FacebookConfig = None
    whatsapp: WhatsAppConfig = None
    ai: AIConfig = None
    market: MarketConfig = None
    check_interval_seconds: int = 300
    log_level: str = "INFO"

    def __post_init__(self):
        self.facebook = FacebookConfig()
        self.whatsapp = WhatsAppConfig()
        self.ai = AIConfig()
        self.market = MarketConfig()


config = BotConfig()
