"""Daily bars through Vibe-Trading's Yahoo loader, cached as CSV under data/prices/."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from tradeagent.config import PROJECT_ROOT

CACHE = PROJECT_ROOT / "data" / "prices"
log = logging.getLogger(__name__)


def _path(cache: Path, symbol: str, start: str, end: str) -> Path:
    return cache / f"{symbol}_{start}_{end}.csv"


def daily_bars(symbols: list[str], start: str, end: str, cache: Path = CACHE) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Return ({symbol: adjusted OHLCV}, [symbols that could not be fetched])."""
    cache.mkdir(parents=True, exist_ok=True)
    out: dict[str, pd.DataFrame] = {}
    todo = []
    for s in symbols:
        p = _path(cache, s, start, end)
        if p.exists():
            out[s] = pd.read_csv(p, index_col=0, parse_dates=True)
        else:
            todo.append(s)
    if todo:
        from backtest.loaders.yahoo_loader import DataLoader  # Vibe-Trading, pinned

        fetched = DataLoader().fetch([f"{s}.US" for s in todo], start, end)
        for s in todo:
            df = fetched.get(f"{s}.US")
            if df is None or df.empty:
                continue
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            df.index.name = "date"
            df.to_csv(_path(cache, s, start, end))
            out[s] = df
    missing = [s for s in symbols if s not in out]
    if missing:
        log.warning("no data for %s", missing)
    return out, missing
