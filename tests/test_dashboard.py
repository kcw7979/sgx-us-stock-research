"""Streamlit tests are offline; the sample data here is synthetic TEST DATA ONLY."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from equity_research.providers import DataError
from equity_research.universe import UNIVERSE

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def test_dashboard_blocks_on_missing_data():
    with patch("equity_research.storage.load_snapshot", side_effect=DataError("No usable snapshot")):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
    assert not app.exception
    assert "No usable snapshot" in app.error[0].value
    assert not app.dataframe


def test_dashboard_comparison_and_allocation_render():
    frames = {}
    for symbol, equity in UNIVERSE.items():
        dates = pd.bdate_range("2024-01-01", periods=270)
        frames[symbol] = pd.DataFrame({
            "date": dates, "adj_close": np.arange(100., 370.), "close": np.arange(100., 370.),
            "symbol": symbol, "currency": equity.currency, "exchange": equity.exchange,
            "provider": "MOCK TEST DATA ONLY",
            "source_timestamp": dates.tz_localize("UTC"),
            "retrieved_at": pd.Timestamp("2026-01-01", tz="UTC"),
            "session_close": dates.tz_localize("UTC") + pd.Timedelta(hours=20),
        })
    # This UI-only mock bypasses storage validation. Calendar validation has separate tests.
    with patch("equity_research.storage.load_snapshot", return_value=frames):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
    assert not app.exception
    assert len(app.dataframe) >= 2
    assert len(app.dataframe[0].value) == 4
    assert not app.error
