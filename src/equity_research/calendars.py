from datetime import date

import pandas as pd
import pandas_market_calendars as mcal

from .universe import Equity

# Allow time for end-of-day vendors to publish finalized daily bars.
PUBLICATION_LAG = pd.Timedelta(hours=2)


def schedule(equity: Equity, start: date, end: date) -> pd.DataFrame:
    return mcal.get_calendar(equity.calendar).schedule(start_date=start, end_date=end)


def completed_sessions(equity: Equity, start: date, now: pd.Timestamp) -> pd.DataFrame:
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("now must have a timezone")
    sessions = schedule(equity, start, now.tz_convert(equity.timezone).date())
    return sessions.loc[sessions.market_close + PUBLICATION_LAG <= now]
