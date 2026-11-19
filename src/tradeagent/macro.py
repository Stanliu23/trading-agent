"""Macro watch for holdings: rates & the Fed, politics & trade.

Plain code, no AI. Headlines come from official feeds (Fed press releases) and news feeds (Google News,
which names each publisher, and Yahoo). Headlines about the same story are grouped; a story is
*confirmed* only with 2 independent publishers, or 1 official source plus 1 news report. Unconfirmed
stories are held and re-checked on the next run; they never reach an email.

Numbers attached to a story (a holding's sensitivity to the 10-year yield, its moves after past Fed
rate changes) are measured from price history, never guessed.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import requests

from tradeagent.config import Config

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh) tradeagent/0.1"}
FED_RSS = "https://www.federalreserve.gov/feeds/press_all.xml"
GNEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

# Fixed keyword lists (set 2026-11-19). A headline belongs to a factor if it contains any phrase.
FACTOR_WORDS: dict[str, list[str]] = {
    "rates_fed": ["federal reserve", "federal open market committee", "the fed", "fed's", "fed ", "fomc",
                  "interest rate", "rate cut", "rate hike",
                  "rate decision", "powell", "treasury yield", "10-year yield", "bond yields"],
    "politics_trade": ["tariff", "sanction", "trade war", "trade deal", "export control", "import duty", "antitrust",
                       "executive order", "regulation", "regulator", "congress", "white house", "election", "embargo"],
}
GNEWS_QUERIES = {"rates_fed": '"Federal Reserve" OR FOMC OR "interest rates"',
                 "politics_trade": "tariffs OR sanctions OR \"trade deal\" OR \"export controls\""}
OFFICIAL_PUBLISHERS = ("federal reserve", "u.s. securities and exchange commission", "sec.gov",
                       "bureau of labor statistics", "u.s. treasury", "department of the treasury", "fred")
BROAD_MARKET_RE = re.compile(r"\b(stock market|stocks|wall street|s&p 500|s&p|nasdaq|dow jones)\b")

# Names and sectors for the traded watchlist, used to decide whether a politics/trade story concerns a holding.
NAMES: dict[str, tuple[str, str]] = {
    "AAPL": ("Apple", "tech"), "MSFT": ("Microsoft", "tech"), "AMZN": ("Amazon", "retail"), "GOOGL": ("Google", "tech"),
    "META": ("Meta", "tech"), "NVDA": ("Nvidia", "semiconductors"), "JPM": ("JPMorgan", "banks"), "V": ("Visa", "payments"),
    "MA": ("Mastercard", "payments"), "UNH": ("UnitedHealth", "health"), "JNJ": ("Johnson & Johnson", "pharma"),
    "PG": ("Procter & Gamble", "consumer"), "HD": ("Home Depot", "retail"), "XOM": ("Exxon", "oil"), "CVX": ("Chevron", "oil"),
    "KO": ("Coca-Cola", "consumer"), "PEP": ("PepsiCo", "consumer"), "COST": ("Costco", "retail"), "WMT": ("Walmart", "retail"),
    "MRK": ("Merck", "pharma"), "ABBV": ("AbbVie", "pharma"), "PFE": ("Pfizer", "pharma"), "CSCO": ("Cisco", "tech"),
    "ORCL": ("Oracle", "tech"), "ADBE": ("Adobe", "tech"), "CRM": ("Salesforce", "tech"), "INTC": ("Intel", "semiconductors"),
    "AMD": ("AMD", "semiconductors"), "QCOM": ("Qualcomm", "semiconductors"), "TXN": ("Texas Instruments", "semiconductors"),
    "AVGO": ("Broadcom", "semiconductors"), "NFLX": ("Netflix", "media"), "DIS": ("Disney", "media"),
    "MCD": ("McDonald's", "restaurants"), "NKE": ("Nike", "apparel"), "BAC": ("Bank of America", "banks"),
    "WFC": ("Wells Fargo", "banks"), "LLY": ("Eli Lilly", "pharma"), "TMO": ("Thermo Fisher", "health"), "UNP": ("Union Pacific", "railroads"),
    "XLK": ("technology sector", "tech"), "XLF": ("financial sector", "banks"), "XLE": ("energy sector", "oil"),
    "XLV": ("health care sector", "health"), "XLI": ("industrial sector", "industrials"), "XLY": ("consumer discretionary", "retail"),
    "XLP": ("consumer staples", "consumer"), "XLU": ("utilities", "utilities"), "XLB": ("materials sector", "materials"),
    "EFA": ("international stocks", "international"), "EEM": ("emerging markets", "international"),
    "TLT": ("long-term Treasuries", "bonds"), "IEF": ("Treasuries", "bonds"), "GLD": ("gold", "gold"),
}
SECTOR_WORDS: dict[str, list[str]] = {
    "semiconductors": ["chip", "semiconductor"], "tech": ["tech ", "technology", "software"], "banks": ["bank", "lender"],
    "payments": ["payment", "card fees", "swipe fee"], "pharma": ["drug", "pharma"], "health": ["health", "medicare"],
    "oil": ["oil", "crude", "energy"], "retail": ["retail", "consumer"], "consumer": ["consumer", "food", "grocery"],
    "media": ["media", "streaming"], "restaurants": ["restaurant"], "apparel": ["apparel", "footwear"],
    "railroads": ["rail"], "industrials": ["industrial", "manufactur"], "utilities": ["utilit", "power grid"],
    "materials": ["steel", "aluminum", "copper", "materials"], "international": ["china", "europe", "emerging", "global"],
    "bonds": ["treasury", "bond"], "gold": ["gold"],
}
BROAD_ETFS = {"VTI", "QQQ", "SCHD", "SPY", "DIA", "IWM"}
_STOP = set("a an the of to in on for and or as at by with from is are be its it this that after over new says".split())


@dataclass(frozen=True)
class Item:
    title: str
    publisher: str
    published: datetime
    link: str = ""

    @property
    def official(self) -> bool:
        p = self.publisher.lower()
        return any(o in p for o in OFFICIAL_PUBLISHERS)


@dataclass
class Story:
    factor: str
    items: list[Item] = field(default_factory=list)

    @property
    def publishers(self) -> set[str]:
        return {i.publisher for i in self.items}

    @property
    def headline(self) -> Item:
        # Prefer an official item, then the earliest report.
        return sorted(self.items, key=lambda i: (not i.official, i.published))[0]

    def confirmed(self, config: Config) -> bool:
        pubs = self.publishers
        official = {i.publisher for i in self.items if i.official}
        news = pubs - official
        if config.macro.official_counts_as_one and official and news:
            return True
        return len(pubs) >= config.macro.min_publishers


# --- fetching ------------------------------------------------------------------

def _parse_rss(content: bytes, default_publisher: str) -> list[Item]:
    root = ET.fromstring(content)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = it.find("source")
        publisher = (src.text or "").strip() if src is not None and src.text else default_publisher
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(publisher) - 3].strip()
        publisher = publisher.split(" - ")[0].strip()        # "ABC News - Breaking News, ..." -> "ABC News"
        pub = it.findtext("pubDate")
        try:
            when = parsedate_to_datetime(pub) if pub else None
        except (TypeError, ValueError):
            when = None
        if title and when:
            out.append(Item(title, publisher, when.astimezone(timezone.utc), it.findtext("link") or ""))
    return out


def _get(url: str) -> bytes:
    r = requests.get(url, headers=_UA, timeout=20)
    r.raise_for_status()
    return r.content


def fetch_items(config: Config, yahoo_symbols: Iterable[str] = ()) -> list[Item]:
    """Fetch every configured feed once. A failed feed is skipped (its items simply can't confirm anything)."""
    items: list[Item] = []
    feeds = [(FED_RSS, "Federal Reserve")]
    feeds += [(GNEWS.format(q=quote_plus(GNEWS_QUERIES[f] + " when:3d")), "Google News") for f in config.macro.factors]
    feeds += [(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={s}&region=US&lang=en-US", "Yahoo Finance")
              for s in yahoo_symbols]
    for url, publisher in feeds:
        try:
            items += _parse_rss(_get(url), publisher)
        except Exception:
            continue
    return items


def fred_series(series: str) -> pd.Series:
    df = pd.read_csv(io.BytesIO(_get(FRED_CSV.format(series=series))))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    return pd.to_numeric(df.set_index("date")["value"], errors="coerce").dropna()


# --- classifying and grouping ------------------------------------------------------

def factor_of(title: str, factors: Iterable[str]) -> Optional[str]:
    t = " " + title.lower() + " "
    for f in factors:
        if any(w in t for w in FACTOR_WORDS[f]):
            return f
    return None


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", title.lower()) if w not in _STOP and len(w) > 2}


def group_stories(items: list[Item], config: Config, now: datetime) -> list[Story]:
    """Group recent headlines into stories (same factor, enough word overlap, within the time window)."""
    window = timedelta(hours=config.macro.story_window_hours)
    recent = sorted((i for i in items if now - i.published <= window), key=lambda i: i.published)
    stories: list[Story] = []
    for it in recent:
        f = factor_of(it.title, config.macro.factors)
        if not f:
            continue
        w = _words(it.title)
        best, best_score = None, 0.0
        for st in stories:
            if st.factor != f:
                continue
            score = max(len(w & _words(x.title)) / max(1, len(w | _words(x.title))) for x in st.items)
            if score > best_score:
                best, best_score = st, score
        if best is not None and best_score >= config.macro.title_match:
            if it.publisher not in best.publishers or it.official:
                best.items.append(it)
        else:
            stories.append(Story(f, [it]))
    return stories


def relevant_holdings(story: Story, holdings: Iterable[str]) -> list[str]:
    """Rates/Fed stories concern every holding; politics/trade stories only holdings they name or whose sector
    they mention (broad-market funds when the story is about the market as a whole)."""
    holdings = list(holdings)
    if story.factor == "rates_fed":
        return holdings
    text = " " + " ".join(i.title.lower() for i in story.items) + " "
    out = []
    for h in holdings:
        name, sector = NAMES.get(h, (h, ""))
        named = name.lower() in text or f" {h.lower()} " in text
        sector_hit = any(w in text for w in SECTOR_WORDS.get(sector, []))
        broad = h in BROAD_ETFS and bool(BROAD_MARKET_RE.search(text))
        if named or sector_hit or broad:
            out.append(h)
    return out


# --- measured effects ----------------------------------------------------------------

@dataclass(frozen=True)
class Sensitivity:
    symbol: str
    per_10bp: Optional[float]     # % move per +0.10-pt change in the 10-year yield
    t: Optional[float]
    n: int
    measured: bool

    def line(self) -> str:
        if self.per_10bp is None:
            return f"{self.symbol}: not enough history to measure rate sensitivity."
        verdict = "measured" if self.measured else "not statistically clear"
        return (f"{self.symbol}: {self.per_10bp:+.2%} on days the 10-year yield rose 0.10 pt "
                f"(last {self.n} sessions, t = {self.t:+.1f}, {verdict})")


def rate_sensitivity(prices: pd.DataFrame, yield10: pd.Series, symbol: str, config: Config) -> Sensitivity:
    """Regression of the holding's daily return on the daily change in the 10-year yield (percentage points)."""
    ret = prices["close"].pct_change()
    dy = yield10.reindex(prices.index).ffill().diff()
    df = pd.concat([ret, dy], axis=1, keys=["r", "dy"]).dropna().tail(config.macro.rate_sensitivity_lookback)
    if len(df) < 60 or df["dy"].std() == 0:
        return Sensitivity(symbol, None, None, len(df), False)
    x, y = df["dy"].to_numpy(), df["r"].to_numpy()
    xc = x - x.mean()
    beta = float((xc * (y - y.mean())).sum() / (xc ** 2).sum())
    resid = y - y.mean() - beta * xc
    se = float(np.sqrt((resid ** 2).sum() / (len(x) - 2) / (xc ** 2).sum()))
    t = beta / se if se > 0 else 0.0
    return Sensitivity(symbol, beta * 0.10, t, len(df), abs(t) >= config.macro.min_abs_t)


def fed_change_days(target_upper: pd.Series) -> dict[str, list[pd.Timestamp]]:
    """Days the Fed's target range changed, split into hikes and cuts."""
    d = target_upper.diff()
    return {"hike": list(d[d > 0].index), "cut": list(d[d < 0].index)}


@dataclass(frozen=True)
class FedImpact:
    kind: str                     # "hike" or "cut"
    n: int
    median: Optional[float]
    same_sign: Optional[float]
    measured: bool


def fed_move_impact(prices: pd.DataFrame, days: list[pd.Timestamp], config: Config, kind: str,
                    horizon: int = 5) -> FedImpact:
    """Median return over ``horizon`` sessions after past Fed changes, minus the holding's typical return.
    Counts as measured only under the same rule as news impact (count, size, direction)."""
    close = prices["close"]
    typical = close.pct_change(horizon).median()
    rets = []
    for d in days:
        pos = close.index.searchsorted(d)
        if 0 < pos and pos + horizon - 1 < len(close):
            rets.append(close.iloc[pos + horizon - 1] / close.iloc[pos - 1] - 1 - typical)
    if not rets:
        return FedImpact(kind, 0, None, None, False)
    med = float(np.median(rets))
    same = float(np.mean([(r > 0) if med >= 0 else (r < 0) for r in rets]))
    nw = config.news
    measured = len(rets) >= nw.min_similar_events and abs(med) >= nw.measured_min_abs_median and same >= nw.measured_min_same_sign
    return FedImpact(kind, len(rets), med, same, measured)


# --- one monitoring run -----------------------------------------------------------------

@dataclass
class MacroReport:
    confirmed: list[tuple[Story, list[str]]]      # (story, holdings it concerns)
    held: list[Story]                              # one-source stories, re-checked next run

    def held_count(self) -> int:
        return len(self.held)


def run_once(items: list[Item], holdings: Iterable[str], config: Config, now: Optional[datetime] = None,
             already_reported: Iterable[str] = ()) -> MacroReport:
    now = now or datetime.now(timezone.utc)
    seen = set(already_reported)
    confirmed, held = [], []
    for st in group_stories(items, config, now):
        key = story_key(st)
        if key in seen:
            continue
        who = relevant_holdings(st, holdings)
        if not who:
            continue
        (confirmed if st.confirmed(config) else held).append((st, who) if st.confirmed(config) else st)
    return MacroReport(confirmed, held)


def story_key(st: Story) -> str:
    first = sorted(st.items, key=lambda i: i.published)[0]
    return f"{st.factor}:{first.published:%Y%m%d}:{' '.join(sorted(_words(first.title)))[:80]}"


MAX_STORIES_PER_FACTOR = 3


def email_lines(report: MacroReport, sensitivity: dict[str, Sensitivity],
                fed_impact: dict[str, list[FedImpact]], config: Config):
    """Lines for the digest's 'Macro on your holdings' section. Only stories that touch a holding with a
    measured link are listed (at most 3 per factor, most-reported first); every line names its sources."""
    from tradeagent.emailer import Line

    def measured_for(sym: str, factor: str) -> bool:
        if factor != "rates_fed":
            return False      # no historical measure for politics/trade headlines yet
        s = sensitivity.get(sym)
        return bool((s and s.measured) or any(f.measured for f in fed_impact.get(sym, [])))

    lines, hidden = [], 0
    for factor, label in (("rates_fed", "Rates & Fed"), ("politics_trade", "Politics & trade")):
        stories = [(st, who) for st, who in report.confirmed if st.factor == factor]
        shown = [(st, who) for st, who in stories if any(measured_for(h, factor) for h in who)]
        shown.sort(key=lambda x: -len(x[0].publishers))
        hidden += len(stories) - min(len(shown), MAX_STORIES_PER_FACTOR)
        for st, _ in shown[:MAX_STORIES_PER_FACTOR]:
            h = st.headline
            pubs = sorted(st.publishers, key=lambda p: (p != h.publisher, p))
            lines.append(Line(f"{label}: {h.title}", " + ".join(pubs[:3]), "strong"))
        if factor == "rates_fed" and shown:
            quiet = []
            for sym in sorted({x for _, who in shown for x in who}):
                s = sensitivity.get(sym)
                parts = [s.line()] if s is not None and s.measured else []
                fed = [f"after past Fed {f.kind}s {f.median:+.1%} vs its typical 5 days ({f.n} events, "
                       f"{f.same_sign:.0%} same direction)" for f in fed_impact.get(sym, []) if f.measured]
                if fed and not parts:
                    fed[0] = f"{sym}: " + fed[0]
                parts += fed
                if parts:
                    lines.append(Line("  " + "; ".join(parts), "FRED + prices"))
                else:
                    quiet.append(sym)
            if quiet:
                lines.append(Line(f"  {', '.join(quiet)}: no measured link to rates; context only.", tone="muted"))
    if hidden:
        lines.append(Line(f"{hidden} more confirmed macro stories touch your holdings but have no measured price link; "
                          "not shown.", tone="muted"))
    if report.held:
        lines.append(Line(f"{len(report.held)} one-source macro items held until a second source confirms.", tone="muted"))
    return lines
