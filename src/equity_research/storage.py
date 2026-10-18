"""Versioned snapshots with an atomic pointer. A failed refresh blocks consumers."""
import json
import os
from pathlib import Path
from uuid import uuid4

import pandas as pd

from .calendars import completed_sessions
from .providers import DataError
from .universe import UNIVERSE
from .validation import validate_bars


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def save_snapshot(root: Path, frames: dict[str, pd.DataFrame], now: pd.Timestamp) -> None:
    version = uuid4().hex
    folder = root / "snapshots" / version
    folder.mkdir(parents=True)
    for symbol, frame in frames.items():
        frame.to_csv(folder / f"{symbol}.csv", index=False)
        frame.to_parquet(folder / f"{symbol}.parquet", index=False)
    write_json(root / "status.json", {
        "status": "ok", "version": version, "refreshed_at": now.isoformat(),
        "symbols": list(frames), "schema_version": 1,
    })


def load_snapshot(root: Path, now: pd.Timestamp | None = None) -> dict[str, pd.DataFrame]:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    try:
        status = json.loads((root / "status.json").read_text())
        if status.get("status") != "ok":
            raise DataError("Last refresh failed: " + status.get("error", "unknown error"))
        if status.get("schema_version") != 1 or set(status["symbols"]) != set(UNIVERSE):
            raise DataError("Unsupported or incomplete snapshot")
        version = status["version"]
        if len(version) != 32 or any(c not in "0123456789abcdef" for c in version):
            raise DataError("Invalid snapshot version")
        frames = {}
        for symbol, equity in UNIVERSE.items():
            frame = pd.read_parquet(root / "snapshots" / version / f"{symbol}.parquet")
            expected = completed_sessions(equity, pd.Timestamp(frame.date.min()).date(), now)
            frames[symbol] = validate_bars(frame, equity, expected, now)
        return frames
    except DataError:
        raise
    except Exception as exc:
        raise DataError(f"No usable snapshot: {type(exc).__name__}. Run a data refresh.") from exc
