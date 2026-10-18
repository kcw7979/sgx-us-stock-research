from datetime import date
from typing import Protocol

import pandas as pd
import yfinance as yf

from .universe import Equity


class DataError(RuntimeError):
    """Unavailable, incomplete or invalid market data; never substitute prices."""


class MarketDataProvider(Protocol):
    name: str

    def daily(self, equity: Equity, start: date, end: date) -> pd.DataFrame:
        """Return daily bars for inclusive session dates, with UTC provenance timestamps."""
        ...


class YahooFinanceProvider:
    name = "Yahoo Finance via yfinance"

    def daily(self, equity: Equity, start: date, end: date) -> pd.DataFrame:
        try:
            ticker = yf.Ticker(equity.provider_symbol)
            raw = ticker.history(
                start=start.isoformat(), end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat(),
                interval="1d", auto_adjust=False, actions=False, repair=False,
                raise_errors=True, timeout=30,
            )
            if raw.empty or "Adj Close" not in raw:
                raise DataError("Provider returned no adjusted daily prices")
            metadata = ticker.get_history_metadata()
            if metadata.get("currency") != equity.currency:
                raise DataError("Provider currency is missing or does not match the instrument")
            index = pd.DatetimeIndex(raw.index)
            if index.tz is None:
                raise DataError("Provider daily timestamps lack a timezone")
            frame = raw.rename(columns={
                "Open": "open", "High": "high", "Low": "low", "Close": "close",
                "Adj Close": "adj_close", "Volume": "volume",
            })[["open", "high", "low", "close", "adj_close", "volume"]].reset_index(drop=True)
            frame.insert(0, "date", index.tz_convert(equity.timezone).date)
            # Timestamp of the vendor's daily bar, NOT a claimed publication timestamp.
            frame["source_timestamp"] = index.tz_convert("UTC")
            frame["retrieved_at"] = pd.Timestamp.now(tz="UTC")
            frame["symbol"] = equity.symbol
            frame["exchange"] = equity.exchange
            frame["currency"] = equity.currency
            frame["provider"] = self.name
            return frame
        except DataError:
            raise
        except Exception as exc:
            raise DataError(f"{equity.symbol}: Yahoo Finance request failed ({type(exc).__name__})") from exc
