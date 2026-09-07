import logging
import re
import ssl
import urllib.request
from typing import Any, Dict, List

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

DSE_BASE_URL = "https://dsebd.org"
DSE_LATEST_URL = "https://dsebd.org/latest_share_price_scroll_l.php"
DSE_QUOTES_URL = "https://www.dsebd.org/datafile/quotes.txt"

_session = requests.Session()
_session.trust_env = False
_session.verify = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
})
_adapter = HTTPAdapter(max_retries=1)
_session.mount("https://", _adapter)

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_dse_market_summary() -> Dict[str, Any]:
    try:
        resp = _session.get(DSE_LATEST_URL, timeout=20)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        rows = _parse_dse_html(resp.text)
        return {
            "source": "dsebd.org",
            "total_scripts": len(rows),
            "scraped_at": __import__("datetime").datetime.now().isoformat(),
            "rows": rows[:500],
        }
    except Exception as e:
        logger.error(f"DSE fetch failed: {e}")
        try:
            return fetch_dse_quotes()
        except Exception:
            return {"source": "dsebd.org", "error": str(e), "rows": []}


def fetch_dse_quotes() -> Dict[str, Any]:
    try:
        resp = _session.get(DSE_QUOTES_URL, timeout=20)
        resp.raise_for_status()
        resp.encoding = "latin-1"
        rows = []
        header_line = None
        for line in resp.text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("price & index"):
                header_line = line
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    rows.append({
                        "ticker": parts[0],
                        "last_price": float(parts[1]),
                        "close_price": float(parts[2]) if len(parts) > 2 else None,
                    })
                except ValueError:
                    continue
        return {
            "source": "dsebd.org/datafile/quotes.txt",
            "header": header_line,
            "total_scripts": len(rows),
            "scraped_at": __import__("datetime").datetime.now().isoformat(),
            "rows": rows[:500],
        }
    except Exception as e:
        logger.error(f"DSE quotes fetch failed: {e}")
        return {"source": "dsebd.org/datafile/quotes.txt", "error": str(e), "rows": []}


def _parse_dse_html(html: str) -> List[Dict]:
    rows: List[Dict] = []
    try:
        for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
            seg = row_match.group(1)
            cells = re.split(r"<td[^>]*>", seg)
            if len(cells) < 11:
                continue
            values = [_clean_cell(c) for c in cells[1:]]
            if len(values) < 10:
                continue
            ticker = values[1]
            if not ticker or not ticker.replace(".", "").isalnum():
                continue
            try:
                rows.append({
                    "ticker": ticker,
                    "last_price": _to_float(values[2]),
                    "high": _to_float(values[3]),
                    "low": _to_float(values[4]),
                    "close_price": _to_float(values[5]),
                    "ycp": _to_float(values[6]),
                    "change": _to_float(values[7]),
                    "trade_count": _to_float(values[8]),
                    "value_mn": _to_float(values[9]),
                    "volume": _to_float(values[10]) if len(values) > 10 else None,
                })
            except (ValueError, IndexError):
                continue
    except Exception as e:
        logger.error(f"DSE parse error: {e}")
    return rows


def _clean_cell(cell: str) -> str:
    inner = re.sub(r"<[^>]+>", " ", cell)
    inner = inner.split("</td>", 1)[0]
    return " ".join(inner.split()).replace(",", "").replace("&nbsp;", " ")


def _to_float(value: str) -> float:
    if not value or value in ("-", "—"):
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def fetch_dse_index() -> Dict[str, Any]:
    try:
        resp = _session.get(DSE_LATEST_URL, timeout=20)
        resp.raise_for_status()
        return {
            "exchange": "Dhaka Stock Exchange",
            "index": "DSEX",
            "error": "Index value requires additional parsing - showing market summary size",
            "size_bytes": len(resp.text),
        }
    except Exception as e:
        return {"exchange": "Dhaka Stock Exchange", "error": str(e)}