from datetime import timedelta
from pathlib import Path

import pandas as pd

from .calendars import completed_sessions
from .providers import DataError, MarketDataProvider
from .storage import save_snapshot, write_json
from .universe import UNIVERSE
from .validation import validate_bars


def refresh(provider: MarketDataProvider, root: Path,
            now: pd.Timestamp | None = None) -> dict[str, pd.DataFrame]:
    clock = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if clock.tzinfo is None:
        raise ValueError("Refresh clock must be timezone-aware")
    root = Path(root)
    write_json(root / "status.json", {"status": "refreshing", "attempted_at": clock.isoformat(),
                                      "error": "Refresh in progress or interrupted; retry refresh"})
    try:
        frames = {}
        for symbol, equity in UNIVERSE.items():
            start = clock.date() - timedelta(days=550)
            expected = completed_sessions(equity, start, clock)
            if expected.empty:
                raise DataError(f"{symbol}: no completed sessions")
            raw = provider.daily(equity, expected.index[0].date(), expected.index[-1].date())
            # Real retrieval happens after the initial clock; validate against wall time.
            validation_now = max(clock, pd.Timestamp.now(tz="UTC")) if now is None else clock
            frames[symbol] = validate_bars(raw, equity, expected, validation_now)
        save_snapshot(root, frames, clock)
        return frames
    except Exception as exc:
        message = str(exc) if isinstance(exc, DataError) else f"Refresh failed ({type(exc).__name__})"
        write_json(root / "status.json", {"status": "error", "attempted_at": clock.isoformat(),
                                          "error": message})
        raise DataError(message) from exc
