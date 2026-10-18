import math
from collections.abc import Mapping

import numpy as np
import pandas as pd


def positive(value: float, label: str) -> None:
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite and positive")


def allocate(capital: float, weights: Mapping[str, float]) -> pd.DataFrame:
    """Explicit weights in ONE base currency; unallocated balance remains cash."""
    positive(capital, "Capital")
    if not weights or any(not np.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError("Weights must be finite and non-negative")
    total = sum(weights.values())
    if total > 1 + 1e-12:
        raise ValueError("Weights exceed 100%")
    rows = [{"symbol": s, "weight": w, "base_amount": capital * w} for s, w in weights.items()]
    rows.append({"symbol": "CASH", "weight": max(0, 1-total), "base_amount": capital * max(0, 1-total)})
    return pd.DataFrame(rows)


def position_size(capital: float, risk_fraction: float, entry: float, stop: float,
                  fx_to_base: float, allocation_fraction: float = 1, lot_size: int = 1) -> dict:
    """Long-only sizing with user supplied current quote/FX, bounded by cash allocation.

    entry and stop are unadjusted quote-currency prices; FX = base units per quote unit.
    """
    for value, label in [(capital, "Capital"), (entry, "Entry"), (stop, "Stop"),
                         (fx_to_base, "FX rate")]:
        positive(value, label)
    if not 0 < risk_fraction <= 1 or not 0 < allocation_fraction <= 1:
        raise ValueError("Risk and allocation fractions must be in (0, 1]")
    if stop >= entry or isinstance(lot_size, bool) or not isinstance(lot_size, int) or lot_size < 1:
        raise ValueError("Stop must be below entry; lot size must be a positive integer")
    per_share_risk = (entry - stop) * fx_to_base
    units = min(capital * risk_fraction / per_share_risk,
                capital * allocation_fraction / (entry * fx_to_base))
    shares = math.floor(units / lot_size) * lot_size
    return {"shares": shares, "cost_base": shares * entry * fx_to_base,
            "risk_base": shares * per_share_risk, "risk_budget_base": capital * risk_fraction}
