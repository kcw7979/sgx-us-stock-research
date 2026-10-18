# SGX + US Stock Research — Phase 1

A Python 3.12 research platform for ST Engineering (`S63` / `S63.SI`), DBS
(`D05` / `D05.SI`), Nvidia (`NVDA`) and Microsoft (`MSFT`). Includes validated
end-of-day ingestion, technical indicators, portfolio calculators, Streamlit,
Excel exports and scheduled GitHub Actions. No brokerage integration or trading.

## Cloud setup — no local PC

1. Open this repository in **GitHub Codespaces** (Code → Codespaces → Create).
   The included devcontainer selects Python 3.12 and installs development dependencies.
2. In its browser terminal run:

   ```bash
   python --version  # The Codespaces devcontainer provides Python 3.12.x.
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -e '.[dev]'
   pytest -q
   ruff check .
   equity-refresh --data-dir data --excel exports/equity-research.xlsx
   streamlit run app.py --server.address 0.0.0.0
   ```

3. Open forwarded port 8501 in Codespaces. Keep its visibility private.
4. If Yahoo cannot supply prices, the refresh exits nonzero with `DATA ERROR`.
   The dashboard displays the reason and blocks analytics. There is no demo mode.

Python dependencies use compatible version ranges in `pyproject.toml`. This is
not a fully locked environment; record resolved versions (`pip freeze`) in your
cloud deployment for reproducibility. CI and the refresh job use Python 3.12.

## Streamlit cloud deployment

1. Connect the repository to Streamlit Community Cloud (or a private Streamlit
   host), choose the review/merged branch, and set the entrypoint to `app.py`.
2. Select **Python 3.12** in the deployment settings. `requirements.txt` installs
   the package and its declared dependencies.
3. Open the dashboard and select **Refresh market data**. First launch has no
   prices. A failed refresh shows a clear error; no generated substitute appears.
4. For confidential research, use private app access and verify host access
   controls and the applicable market-data licensing before deployment.

`RESEARCH_DATA_DIR` optionally changes the dashboard's data folder (default:
`data`). No API key is required by the initial adapter. Host storage may be
**ephemeral**: restarts can erase it, requiring another real-data refresh.

The dashboard and Actions run in different cloud filesystems. The scheduled
workflow retains a downloadable snapshot and workbook; it does **not** silently
sync artifacts into Streamlit. In Phase 1, refresh the hosted dashboard with its
button, or restore an authorized Actions artifact's `data/` directory into a
persistent Streamlit host. Automatic artifact-to-dashboard synchronization is
not implemented. No public Git branch is used to distribute market prices.

## Scheduled refresh and exports

After merging to the default branch, enable GitHub Actions and open **Actions →
Daily market data refresh → Run workflow** for the first cloud run. Future runs
are scheduled at **02:30 UTC Tuesday–Saturday**, after the prior US session and
a two-hour publication buffer in both daylight-saving seasons. On holidays the
latest completed session remains valid. GitHub cron can be delayed, runs only on
the default branch, and may be disabled after prolonged inactivity in public
repositories. Check failed-run notifications and run manually when necessary.

Successful runs upload an `equity-research-<run id>` artifact containing:

- `data/status.json`: schema, active snapshot version and refresh timestamp.
- `data/snapshots/<version>/*.csv` and `*.parquet`: the four validated datasets.
- `exports/equity-research.xlsx`: provenance, per-stock indicators and notes.

Artifacts expire after seven days. They inherit repository access; public repo
artifacts should not be treated as private. Confirm your rights to retain and
share the vendor's data before enabling the workflow. Failed refreshes upload
only `status.json` diagnostics and fail the job. Prices and workbooks are ignored
by Git and never automatically committed. Each refresh fetches approximately
550 calendar days again so historical split/dividend adjustments can be revised.
Local snapshot directories accumulate until the host's operator prunes them;
Actions runners start clean on every run.

The dashboard's download includes an optional allocation sheet. The CLI exports
prices and indicators without an allocation sheet unless a caller supplies one
through the Python export API. All workbook timestamps are ISO 8601 strings
with timezone offsets, since Excel has no native timezone-aware datetime type.

## Data contract and validation

`MarketDataProvider` is a Python protocol; implement `daily(equity, start, end)`
to add a licensed provider without changing the analysis modules. Dates are
inclusive session dates. The initial Yahoo adapter explicitly requests
**unadjusted OHLC plus adjusted close**, disables price repair, checks the
provider's currency metadata and preserves these columns:

| Field | Meaning |
| --- | --- |
| `date` | Exchange-local session date |
| `open`, `high`, `low`, `close` | Unadjusted OHLC in native currency |
| `adj_close` | Vendor split/dividend-adjusted closing series |
| `volume` | Vendor-reported daily volume |
| `symbol`, `exchange`, `currency` | Canonical instrument metadata (SGD or USD) |
| `provider` | Data-source attribution |
| `source_timestamp` | Original vendor daily-bar timestamp converted to UTC; **not** publication time |
| `retrieved_at` | Actual adapter retrieval time in UTC |
| `session_close` | Calendar-derived session close in UTC |

`pandas-market-calendars` supplies **SGX** and **NASDAQ** schedules, including
weekends, known holidays, early closes and daylight-saving transitions. Only
sessions whose scheduled close is at least two hours in the past are requested.
This buffer is conservative, not a promise that the vendor has finalized data.
Missing expected sessions cause failure rather than forward filling. Calendar
libraries can lag unexpected closures; review exchange notices and update the
library when necessary. Suspensions/missing bars fail validation and require
investigation; zero-volume sessions are permitted if the provider supplies them.

Validation rejects missing/duplicate/unsorted/unexpected session dates, missing
adjusted close or provenance, nonfinite values, nonpositive prices, negative
volume, inconsistent OHLC, wrong symbol/exchange/currency, naive or future
provenance timestamps, mismatched daily-bar dates and retrieval before close.
Snapshot loading revalidates data against **today's completed sessions**, so
stale snapshots cannot generate dashboard indicators. A refresh marks the store
unavailable before fetching; failure or interruption blocks the prior snapshot.
All four equities must pass before a new immutable snapshot is published through
an atomic status pointer. This is a single-host file store, not a distributed
transaction system; avoid concurrent refresh writers on a shared host.

## Indicator definitions

All calculations use adjusted close in the stock's native currency:

| Indicator | Definition |
| --- | --- |
| MA50 / MA200 | Arithmetic mean over 50 / 200 sessions |
| RSI14 | Wilder smoothing with a 14-change arithmetic seed; flat = 50, no losses = 100 |
| 52-week high / low | Maximum/minimum **adjusted closing price** over 252 sessions (approximate year, not intraday range) |
| Daily return | Current adjusted close / preceding adjusted close − 1 |
| Volatility | Sample standard deviation of 20 daily returns × √252 |

Insufficient history produces missing indicators; no partial-window values are
substituted. Chart comparisons use shared trading dates and normalize each
native-currency series to 100. They are **not** FX-adjusted investor returns.
There is no buy/sell recommendation engine in Phase 1.

## Portfolio allocation and risk sizing

Allocation weights must be nonnegative and total at most 100%; the balance stays
in cash in one selected base currency. Position sizing is long-only and requires
**manual scenario inputs**, not generated quotes: unadjusted entry, stop below
entry, risk fraction, allocation fraction, and an explicit FX rate expressed as
base-currency units per one quote-currency unit. Same-currency FX must be 1 in
the dashboard. SGX board lots default to 100 shares; US lots to one share.
Verify exchange lot rules before using a scenario.

```text
risk budget = portfolio capital × risk fraction
risk per share = (entry − stop) × FX
cash cap = portfolio capital × stock allocation fraction
shares = floor_to_board_lot(min(risk budget / risk per share,
                               cash cap / (entry × FX)))
```

Zero shares is a valid result. Sizing excludes existing positions, portfolio
correlation, fees, slippage, shorting, margin and gap risk. A stop does not
limit realized losses during a gap. FX is user supplied and can be stale; it is
not fetched or verified. Adjusted historical prices must not be used as current
executable quotes. Calculators are research tools, not investment advice.

## Tests and project structure

```text
app.py                         Streamlit dashboard
src/equity_research/
  universe.py                  Instruments, markets, currencies, lot sizes
  providers.py                 Provider protocol and Yahoo adapter
  calendars.py                 Completed exchange sessions
  validation.py                Market-data quality and provenance checks
  pipeline.py / storage.py     Refresh orchestration and versioned CSV/Parquet
  indicators.py                Deterministic price analytics
  portfolio.py                 Allocation and long-only sizing
  export.py / cli.py           Excel and command-line refresh
tests/test_core.py             Formula, sizing and workbook tests
tests/test_market_data.py      Calendar, ingestion, failure and storage tests
tests/test_dashboard.py        Streamlit empty/error and validated-data smoke tests
.github/workflows/             Test and daily refresh jobs
```

Run `pytest -q` for the full offline suite. It uses clearly labeled synthetic
**test-only** datasets and mocks all provider calls; no internet or credentials
are needed to execute tests after dependencies are installed. The dashboard
smoke test also uses mocked storage and never calls a live provider. Core tests
can additionally run with `PYTHONPATH=src python -m unittest discover -s tests -p
test_core.py -v` when pandas, numpy and openpyxl are already installed. This
subset does not replace full pytest verification. `ruff check .` performs linting.

## Dependencies, licenses and source limitations

| Direct dependency | Purpose | Upstream license |
| --- | --- | --- |
| Python 3.12 | Runtime | PSF |
| pandas | Tables/time series | BSD-3-Clause |
| numpy | Numerical calculations | BSD-3-Clause |
| openpyxl | Excel workbooks | MIT |
| Streamlit | Dashboard | Apache-2.0 |
| yfinance | Yahoo Finance adapter | Apache-2.0 |
| pandas-market-calendars | Exchange schedules | MIT |
| pyarrow | Parquet IO | Apache-2.0 |
| pytest (development) | Offline tests | MIT |
| Ruff (development) | Linting | MIT |
| setuptools (build) | Python packaging | MIT |

These are software licenses, **not market-data licenses**. Review upstream and
transitive dependency notices for the resolved versions. yfinance is an
unofficial, community-maintained interface, unaffiliated with Yahoo. Its
[project notice](https://github.com/ranaroussi/yfinance) describes research and
educational intent and warns that Yahoo Finance data is intended for personal
use. Review [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html),
[Yahoo Finance additional terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/finance/index.html)
and exchange/vendor policies (including [SGX market data](https://www.sgx.com/market-data))
before deployment, redistribution or commercial use. A dashboard on a public
URL and downloadable artifacts may constitute redistribution; this repository
does not grant that right. Choose a suitably licensed provider for those uses.

Yahoo can rate-limit, block cloud IPs, change APIs, omit SGX coverage, deliver
late data or revise corporate actions. Adjusted close is vendor-defined and
may not reproduce an exact reinvested total return. There is no service-level
agreement or independent verification of split/dividend adjustments. Provider
unavailability fails explicitly; the software never fills in market prices.

Never commit `.env`, Streamlit secrets, API keys, brokerage credentials or
market-data exports. If a future licensed adapter needs a key, inject it through
GitHub Actions secrets or the host's secret manager; never print it in logs.
Phase 1 contains no secret requirements, live trading code or brokerage clients.
