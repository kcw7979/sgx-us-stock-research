import numpy as np
import pandas as pd


def indicators(bars: pd.DataFrame) -> pd.DataFrame:
    """Session windows; Wilder RSI; annualized sample return volatility (252 sessions)."""
    result = bars.copy()
    price = result.adj_close
    result["ma50"] = price.rolling(50, min_periods=50).mean()
    result["ma200"] = price.rolling(200, min_periods=200).mean()
    delta = price.diff()
    gains, losses = delta.clip(lower=0), -delta.clip(upper=0)
    # Explicit arithmetic seed, followed by Wilder's recursive smoothing.
    rsi = pd.Series(np.nan, index=price.index, dtype=float)
    if len(price) > 14:
        gain, loss = gains.iloc[1:15].mean(), losses.iloc[1:15].mean()
        for i in range(14, len(price)):
            if i > 14:
                gain = (gain * 13 + gains.iloc[i]) / 14
                loss = (loss * 13 + losses.iloc[i]) / 14
            rsi.iloc[i] = 50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
    result["rsi14"] = rsi
    result["high_52w"] = price.rolling(252, min_periods=252).max()
    result["low_52w"] = price.rolling(252, min_periods=252).min()
    result["daily_return"] = price.pct_change(fill_method=None)
    result["volatility_20d"] = result.daily_return.rolling(20, min_periods=20).std(ddof=1) * np.sqrt(252)
    return result
