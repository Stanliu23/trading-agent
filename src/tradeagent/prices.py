"""Daily bars through Vibe-Trading's Yahoo loader, cached as CSV under data/prices/."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from tradeagent.config import PROJECT_ROOT

CACHE = PROJECT_ROOT / "data" / "prices"
log = logging.getLogger(__name__)


def _path(cache: Path, symbol: str, start: str, end: str) -> Path:
    return cache / f"{symbol}_{start}_{end}.csv"


def daily_bars(symbols: list[str], start: str, end: str, cache: Path = CACHE, *, batch_size: int = 6, retries: int = 3,
               pause_s: float = 5.0) -> tuple[dict[str, pd.DataFrame], list[str]]:
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

        loader = DataLoader()
        # Small batches with retries: Yahoo paces requests, and one slow symbol must not sink the rest.
        for i in range(0, len(todo), batch_size):
            batch = todo[i:i + batch_size]
            for attempt in range(retries):
                try:
                    fetched = loader.fetch([f"{s}.US" for s in batch if s not in out], start, end)
                except TimeoutError:
                    log.warning("Yahoo timed out on %s (attempt %d)", batch, attempt + 1)
                    fetched = {}
                for s in batch:
                    df = fetched.get(f"{s}.US")
                    if df is None or df.empty:
                        continue
                    df = df[["open", "high", "low", "close", "volume"]].dropna()
                    df.index.name = "date"
                    df.to_csv(_path(cache, s, start, end))
                    out[s] = df
                if all(s in out for s in batch):
                    break
                time.sleep(pause_s * (attempt + 1))
    missing = [s for s in symbols if s not in out]
    if missing:
        log.warning("no data for %s", missing)
    return out, missing
