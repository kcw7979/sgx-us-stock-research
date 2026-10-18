"""Synthetic prices exist exclusively here for deterministic offline tests."""
import json
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from equity_research.calendars import completed_sessions, schedule
from equity_research.pipeline import refresh
from equity_research.providers import DataError, YahooFinanceProvider
from equity_research.storage import load_snapshot
from equity_research.universe import UNIVERSE
from equity_research.validation import validate_bars

NOW = pd.Timestamp("2025-03-12T03:00:00Z")


def mock_bars(equity, expected, now=NOW):
    """MOCK TEST DATA ONLY; no external network access."""
    prices = 100 + np.arange(len(expected), dtype=float) / 10
    return pd.DataFrame({
        "date": expected.index, "open": prices, "high": prices + 1,
        "low": prices - 1, "close": prices, "adj_close": prices * .9,
        "volume": 1000, "symbol": equity.symbol, "exchange": equity.exchange,
        "currency": equity.currency, "provider": "MOCK TEST DATA ONLY",
        "source_timestamp": expected.index.tz_localize(equity.timezone).tz_convert("UTC"),
        "retrieved_at": now,
    })


class MockProvider:
    name = "MOCK TEST DATA ONLY"

    def daily(self, equity, start, end):
        return mock_bars(equity, schedule(equity, start, end))


def test_us_holidays_early_closes_and_dst():
    equity = UNIVERSE["MSFT"]
    assert schedule(equity, date(2025, 7, 4), date(2025, 7, 4)).empty
    july3 = schedule(equity, date(2025, 7, 3), date(2025, 7, 3))
    assert july3.market_close.iloc[0] == pd.Timestamp("2025-07-03T17:00:00Z")
    before = schedule(equity, date(2025, 3, 7), date(2025, 3, 7))
    after = schedule(equity, date(2025, 3, 10), date(2025, 3, 10))
    assert before.market_close.iloc[0].hour == 21
    assert after.market_close.iloc[0].hour == 20


def test_sgx_holidays_weekends_and_publication_buffer():
    equity = UNIVERSE["S63"]
    assert schedule(equity, date(2025, 1, 29), date(2025, 1, 30)).empty
    assert schedule(equity, date(2025, 3, 8), date(2025, 3, 9)).empty
    close = schedule(equity, date(2025, 3, 11), date(2025, 3, 11)).market_close.iloc[0]
    assert completed_sessions(equity, date(2025, 3, 11), close + pd.Timedelta(minutes=119)).empty
    assert len(completed_sessions(equity, date(2025, 3, 11), close + pd.Timedelta(hours=2))) == 1


def test_calendar_requires_aware_clock():
    with pytest.raises(ValueError, match="timezone"):
        completed_sessions(UNIVERSE["S63"], date(2025, 3, 1), pd.Timestamp("2025-03-12"))


@pytest.fixture
def sample():
    equity = UNIVERSE["NVDA"]
    expected = completed_sessions(equity, date(2025, 3, 1), NOW)
    return equity, expected, mock_bars(equity, expected)


def test_valid_bars_attach_official_session_close(sample):
    equity, expected, frame = sample
    result = validate_bars(frame, equity, expected, NOW)
    assert list(result.session_close) == list(expected.market_close)
    assert str(result.retrieved_at.dt.tz) == "UTC"


@pytest.mark.parametrize("mutation", [
    "empty", "missing_column", "duplicate", "unsorted", "missing_session", "holiday",
    "nan", "inf", "negative_price", "zero_price", "negative_volume", "bad_high", "bad_low",
    "wrong_currency", "wrong_symbol", "wrong_exchange", "missing_provider", "future_time",
    "naive_time", "wrong_source_date", "missing_timestamp", "retrieved_before_close",
])
def test_reject_invalid_data(sample, mutation):
    equity, expected, frame = sample
    if mutation == "empty":
        frame = frame.iloc[:0]
    elif mutation == "missing_column":
        frame = frame.drop(columns="adj_close")
    elif mutation == "duplicate":
        frame = pd.concat([frame, frame.iloc[[-1]]], ignore_index=True)
    elif mutation == "unsorted":
        frame = frame.iloc[::-1]
    elif mutation == "missing_session":
        frame = frame.iloc[:-1]
    elif mutation == "holiday":
        frame.loc[0, "date"] = pd.Timestamp("2025-03-08")
    elif mutation in {"nan", "inf", "negative_price", "zero_price"}:
        frame.loc[0, "adj_close"] = {"nan": np.nan, "inf": np.inf, "negative_price": -1, "zero_price": 0}[mutation]
    elif mutation == "negative_volume":
        frame.loc[0, "volume"] = -1
    elif mutation == "bad_high":
        frame.loc[0, "high"] = 1
    elif mutation == "bad_low":
        frame.loc[0, "low"] = 10000
    elif mutation.startswith("wrong_") and mutation != "wrong_source_date":
        frame.loc[0, mutation.removeprefix("wrong_")] = "WRONG"
    elif mutation == "missing_provider":
        frame.loc[0, "provider"] = ""
    elif mutation == "future_time":
        frame["retrieved_at"] = NOW + pd.Timedelta(days=1)
    elif mutation == "naive_time":
        frame["retrieved_at"] = NOW.tz_localize(None)
    elif mutation == "wrong_source_date":
        frame["source_timestamp"] += pd.Timedelta(days=1)
    elif mutation == "missing_timestamp":
        frame["source_timestamp"] = pd.NaT
    elif mutation == "retrieved_before_close":
        frame["retrieved_at"] = frame.source_timestamp
    with pytest.raises(DataError, match="validation failed"):
        validate_bars(frame, equity, expected, NOW)


def test_snapshot_roundtrip_and_staleness(tmp_path):
    frames = refresh(MockProvider(), tmp_path, NOW)
    loaded = load_snapshot(tmp_path, NOW)
    assert set(loaded) == set(UNIVERSE)
    for symbol in UNIVERSE:
        pd.testing.assert_frame_equal(frames[symbol], loaded[symbol])
    assert len(list(tmp_path.glob("snapshots/*/*.csv"))) == 4
    with pytest.raises(DataError, match="stale"):
        load_snapshot(tmp_path, NOW + pd.Timedelta(days=2))


def test_failed_refresh_blocks_prior_snapshot(tmp_path):
    refresh(MockProvider(), tmp_path, NOW)
    with patch.object(MockProvider, "daily", side_effect=DataError("Provider unavailable")):
        with pytest.raises(DataError, match="Provider unavailable"):
            refresh(MockProvider(), tmp_path, NOW)
    assert json.loads((tmp_path / "status.json").read_text())["status"] == "error"
    with pytest.raises(DataError, match="Last refresh failed"):
        load_snapshot(tmp_path, NOW)


def test_partial_refresh_does_not_publish_snapshot(tmp_path):
    with patch.object(MockProvider, "daily", side_effect=[
        mock_bars(UNIVERSE["S63"], completed_sessions(UNIVERSE["S63"], (NOW - pd.Timedelta(days=550)).date(), NOW)),
        DataError("D05 unavailable"),
    ]):
        with pytest.raises(DataError, match="D05 unavailable"):
            refresh(MockProvider(), tmp_path, NOW)
    assert not (tmp_path / "snapshots").exists()


def test_missing_or_corrupt_storage_is_clear_error(tmp_path):
    with pytest.raises(DataError, match="No usable snapshot"):
        load_snapshot(tmp_path, NOW)
    (tmp_path / "status.json").write_text("not-json")
    with pytest.raises(DataError, match="No usable snapshot"):
        load_snapshot(tmp_path, NOW)


def test_yahoo_failure_has_no_price_fallback():
    with patch("equity_research.providers.yf.Ticker", side_effect=RuntimeError("offline")):
        with pytest.raises(DataError, match="request failed"):
            YahooFinanceProvider().daily(UNIVERSE["S63"], date(2025, 1, 1), date(2025, 2, 1))


def test_yahoo_rejects_empty_response():
    with patch("equity_research.providers.yf.Ticker") as ticker:
        ticker.return_value.history.return_value = pd.DataFrame()
        with pytest.raises(DataError, match="no adjusted"):
            YahooFinanceProvider().daily(UNIVERSE["MSFT"], date(2025, 1, 1), date(2025, 2, 1))


def test_cli_returns_nonzero_without_export_on_failure(tmp_path):
    from equity_research.cli import main
    output = tmp_path / "output.xlsx"
    with patch("sys.argv", ["equity-refresh", "--data-dir", str(tmp_path), "--excel", str(output)]), patch(
        "equity_research.cli.refresh", side_effect=DataError("offline")
    ):
        assert main() == 1
    assert not output.exists()
