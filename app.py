"""Run with: streamlit run app.py"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from equity_research.export import excel_export
from equity_research.indicators import indicators
from equity_research.pipeline import refresh
from equity_research.portfolio import allocate, position_size
from equity_research.providers import DataError, YahooFinanceProvider
from equity_research.storage import load_snapshot
from equity_research.universe import UNIVERSE

st.set_page_config(page_title="SGX + US Research", page_icon="📈", layout="wide")
st.title("SGX + US Equity Research")
st.caption("Daily research • native SGD / USD prices • no trade execution")
root = Path(os.environ.get("RESEARCH_DATA_DIR", "data"))
with st.sidebar:
    st.header("Market data")
    st.write("Yahoo Finance via yfinance. End-of-day data may be delayed.")
    if st.button("Refresh market data", type="primary"):
        try:
            with st.spinner("Fetching and validating all four equities…"):
                refresh(YahooFinanceProvider(), root)
        except DataError as exc:
            st.error(str(exc))
    st.caption("No synthetic price fallback. Failed or stale snapshots block analytics.")

try:
    frames = load_snapshot(root)
except DataError as exc:
    st.error(str(exc))
    st.info("Use Refresh market data to fetch actual prices. No indicators are available until validation passes.")
    st.stop()

selected = st.multiselect("Compare equities", list(UNIVERSE), default=list(UNIVERSE))
if not selected:
    st.info("Select at least one equity.")
    st.stop()
computed = {symbol: indicators(frames[symbol]) for symbol in selected}
latest = pd.DataFrame([frame.iloc[-1] for frame in computed.values()]).set_index("symbol")
st.subheader("Stock comparison")
st.dataframe(latest[["date", "currency", "close", "adj_close", "ma50", "ma200", "rsi14",
                     "high_52w", "low_52w", "daily_return", "volatility_20d"]], width="stretch")
st.caption("MA and RSI use adjusted close. 52-week high/low = 252-session adjusted closing range. "
           "Volatility = annualized 20-session sample return standard deviation. Empty values need more history.")

st.subheader("Relative performance")
prices = pd.concat({s: f.set_index("date").adj_close for s, f in computed.items()}, axis=1)
common = prices.dropna()
if not common.empty:
    st.line_chart(common.div(common.iloc[0]).mul(100), y_label="Native-currency return index (start = 100)")
st.caption("Only common trading dates are compared; no holiday forward fill or FX adjustment.")
focus = st.selectbox("Price and moving averages", selected)
f = computed[focus].set_index("date")
st.line_chart(f[["adj_close", "ma50", "ma200"]], y_label=UNIVERSE[focus].currency)
st.line_chart(f[["rsi14"]], y_label="RSI14")
with st.expander("Source and freshness"):
    st.dataframe(latest[["provider", "source_timestamp", "retrieved_at", "session_close", "exchange", "currency"]])

st.subheader("Portfolio research calculator")
st.caption("Manual scenario inputs; current unadjusted entry and stop prices are required. "
           "FX is user supplied, not market data. Stops do not guarantee a maximum loss.")
base = st.selectbox("Portfolio base currency", ["SGD", "USD"])
capital = st.number_input(f"Portfolio capital ({base})", min_value=1.0, value=100000.0)
weights = {}
cols = st.columns(len(UNIVERSE))
for col, symbol in zip(cols, UNIVERSE):
    weights[symbol] = col.number_input(f"{symbol} allocation %", min_value=0.0, max_value=100.0, value=25.0) / 100
allocation = None
try:
    allocation = allocate(capital, weights)
    st.dataframe(allocation, hide_index=True)
except ValueError as exc:
    st.error(str(exc))

with st.form("sizing"):
    symbol = st.selectbox("Size a position", list(UNIVERSE))
    # FX must always be explicit because Streamlit form fields update together on submit.
    entry = st.number_input("Entry price (selected stock's native currency)", min_value=0.0, value=0.0)
    stop = st.number_input("Stop price (selected stock's native currency)", min_value=0.0, value=0.0)
    fx = st.number_input(f"FX: {base} per 1 unit of stock currency (enter 1 for same currency)", min_value=0.0, value=0.0)
    risk = st.number_input("Capital at risk %", min_value=0.01, max_value=100.0, value=1.0)
    submitted = st.form_submit_button("Calculate position size")
if submitted:
    try:
        if allocation is None:
            raise ValueError("Correct allocation weights before sizing")
        if UNIVERSE[symbol].currency == base and fx != 1:
            raise ValueError("Same-currency FX must equal 1")
        result = position_size(capital, risk / 100, entry, stop, fx,
                               weights[symbol], UNIVERSE[symbol].lot_size)
        st.write({"symbol": symbol, "quote_currency": UNIVERSE[symbol].currency,
                  "base_currency": base, **result})
        st.caption("Whole board lots; excludes fees, slippage, gap risk and existing positions.")
    except ValueError as exc:
        st.error(str(exc))

st.download_button("Download Excel research workbook", excel_export(frames, allocation),
                   file_name="equity-research.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
st.caption("Research only. Verify data and licensing before use or redistribution.")
