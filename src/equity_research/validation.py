import numpy as np
import pandas as pd

from .providers import DataError
from .universe import Equity

PRICE_COLUMNS = ["open", "high", "low", "close", "adj_close"]
REQUIRED = ["date", *PRICE_COLUMNS, "volume", "source_timestamp", "retrieved_at",
            "symbol", "exchange", "currency", "provider"]


def validate_bars(frame: pd.DataFrame, equity: Equity, expected: pd.DataFrame,
                  now: pd.Timestamp) -> pd.DataFrame:
    try:
        if frame.empty or expected.empty:
            raise ValueError("No data or completed sessions in requested interval")
        if set(REQUIRED) - set(frame.columns):
            raise ValueError("Missing required price/provenance columns")
        result = frame.copy()
        dates = pd.to_datetime(result.date, errors="raise")
        if dates.dt.tz is not None or not dates.eq(dates.dt.normalize()).all():
            raise ValueError("Session dates must be timezone-free calendar dates")
        result["date"] = dates.astype("datetime64[ns]")
        if dates.duplicated().any() or not dates.is_monotonic_increasing:
            raise ValueError("Duplicate or unsorted session dates")
        if list(dates) != list(pd.DatetimeIndex(expected.index).tz_localize(None)):
            raise ValueError("Missing, unexpected, stale or incomplete market sessions")
        values = result[PRICE_COLUMNS + ["volume"]].apply(pd.to_numeric, errors="raise")
        if not np.isfinite(values.to_numpy()).all():
            raise ValueError("Non-finite market values")
        if (values[PRICE_COLUMNS] <= 0).any().any() or (values.volume < 0).any():
            raise ValueError("Non-positive prices or negative volume")
        if (values.high < values[["open", "close", "low"]].max(axis=1)).any() or (
            values.low > values[["open", "close", "high"]].min(axis=1)
        ).any():
            raise ValueError("Inconsistent OHLC prices")
        result[PRICE_COLUMNS + ["volume"]] = values
        for key, value in {"symbol": equity.symbol, "exchange": equity.exchange,
                           "currency": equity.currency}.items():
            if not result[key].eq(value).all():
                raise ValueError(f"Incorrect {key} metadata")
        if result.provider.isna().any() or result.provider.astype(str).str.strip().eq("").any():
            raise ValueError("Missing provider attribution")
        for key in ["source_timestamp", "retrieved_at"]:
            if result[key].isna().any():
                raise ValueError("Missing timestamps")
            if any(pd.Timestamp(value).tzinfo is None for value in result[key]):
                raise ValueError("Provenance timestamps must include timezone")
            result[key] = pd.to_datetime(result[key], utc=True).astype("datetime64[ns, UTC]")
        if (result.source_timestamp > result.retrieved_at).any() or (
            result.retrieved_at > now
        ).any():
            raise ValueError("Future or inconsistent provenance timestamps")
        if list(result.source_timestamp.dt.tz_convert(equity.timezone).dt.date) != list(dates.dt.date):
            raise ValueError("Source timestamps do not match session dates")
        closes = pd.Series(expected.market_close.to_numpy(), index=result.index)
        if (result.retrieved_at < closes).any():
            raise ValueError("Bars were retrieved before the session completed")
        result["session_close"] = pd.to_datetime(
            expected.market_close.to_numpy(), utc=True
        ).astype("datetime64[ns, UTC]")
        return result
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise DataError(f"{equity.symbol}: validation failed: {exc}") from exc
