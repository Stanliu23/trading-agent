"""Live Yahoo data: latest quote, earnings dates, news headlines (RSS). SEC filings need a contact email."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
_UA = "Mozilla/5.0 (Macintosh) tradeagent/0.1"


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    prev_close: float
    as_of: datetime


def quote(symbol: str) -> Optional[Quote]:
    import yfinance as yf

    try:
        fi = yf.Ticker(symbol).fast_info
        price, prev = float(fi["lastPrice"]), float(fi["previousClose"])
    except Exception:
        return None
    if not (price > 0 and prev > 0):
        return None
    return Quote(symbol, price, prev, datetime.now().astimezone())


def next_earnings(symbol: str) -> Optional[date]:
    """Next scheduled earnings date from Yahoo's calendar, or None if Yahoo has none."""
    import yfinance as yf

    try:
        dates = yf.Ticker(symbol).calendar.get("Earnings Date") or []
    except Exception:
        return None
    upcoming = sorted(d for d in dates if isinstance(d, date) and d >= date.today())
    return upcoming[0] if upcoming else None


def past_earnings(symbol: str, limit: int = 12) -> list[date]:
    """Recent reported earnings dates (Yahoo), newest first."""
    import yfinance as yf

    try:
        frame = yf.Ticker(symbol).get_earnings_dates(limit=limit)
    except Exception:
        return []
    if frame is None or frame.empty:
        return []
    return sorted({ts.date() for ts in frame.index}, reverse=True)


def headlines(symbol: str, timeout: float = 15) -> list[dict]:
    """Latest Yahoo Finance headlines for a symbol: [{id, title, published, link}]."""
    resp = requests.get(RSS_URL, params={"s": symbol, "region": "US", "lang": "en-US"},
                        headers={"User-Agent": _UA}, timeout=timeout)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    out = []
    for item in root.iter("item"):
        guid = (item.findtext("guid") or item.findtext("link") or "").strip()
        if not guid:
            continue
        pub = item.findtext("pubDate")
        try:
            published = parsedate_to_datetime(pub).isoformat() if pub else None
        except (TypeError, ValueError):
            published = None
        out.append({"id": guid, "title": (item.findtext("title") or "").strip(),
                    "published": published, "link": item.findtext("link")})
    return out


class SecClient:
    """SEC EDGAR requires a real contact in the User-Agent; refuses to run without one."""

    def __init__(self, contact_email: Optional[str]):
        if not contact_email or "@" not in contact_email:
            raise ValueError("SEC EDGAR needs a contact email in config.local.yaml (sec.contact)")
        self.ua = f"tradeagent personal research {contact_email}"
        self._cik: dict[str, str] = {}

    def _get(self, url: str) -> dict:
        time.sleep(0.15)  # SEC allows up to 10 requests/second
        resp = requests.get(url, headers={"User-Agent": self.ua, "Accept": "application/json"}, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def cik(self, symbol: str) -> Optional[str]:
        if not self._cik:
            data = self._get(SEC_TICKERS)
            self._cik = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
        return self._cik.get(symbol.upper())

    def recent_filings(self, symbol: str, forms: tuple[str, ...] = ("8-K", "10-Q", "10-K")) -> list[dict]:
        cik = self.cik(symbol)
        if cik is None:
            return []
        recent = self._get(SEC_SUBMISSIONS.format(cik=cik)).get("filings", {}).get("recent", {})
        out = []
        for acc, form, filed, accepted, items in zip(recent.get("accessionNumber", []), recent.get("form", []),
                                                     recent.get("filingDate", []), recent.get("acceptanceDateTime", []),
                                                     recent.get("items", [])):
            if form in forms:
                out.append({"id": acc, "form": form, "published": filed, "accepted": accepted, "items": items or "",
                            "title": f"{form} filed {filed}" + (f" (items {items})" if items else "")})
        return out
