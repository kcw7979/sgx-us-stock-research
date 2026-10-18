from io import BytesIO

import pandas as pd

from .indicators import indicators


def excel_export(frames: dict[str, pd.DataFrame], allocation: pd.DataFrame | None = None) -> bytes:
    output = BytesIO()
    notes = pd.DataFrame({"Notes": [
        "Research only; no investment recommendation or trade execution.",
        "Prices remain in their native currency; no FX conversion is inferred.",
        "Indicators use adjusted close. 52-week range is 252-session adjusted CLOSE range.",
        "RSI uses Wilder smoothing; volatility is 20-session sample std times sqrt(252).",
        "source_timestamp is the provider daily-bar timestamp, not publication time.",
        "Timestamp strings use ISO 8601 with timezone; generated_at is export time.",
        "Yahoo Finance data usage and redistribution are subject to provider/exchange terms.",
        f"generated_at: {pd.Timestamp.now(tz='UTC').isoformat()}",
    ]})
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        notes.to_excel(writer, sheet_name="Read me", index=False)
        for symbol, bars in frames.items():
            frame = indicators(bars)
            for column in frame:
                if isinstance(frame[column].dtype, pd.DatetimeTZDtype):
                    frame[column] = frame[column].map(lambda value: value.isoformat())
            frame.to_excel(writer, sheet_name=symbol, index=False)
        if allocation is not None:
            allocation.to_excel(writer, sheet_name="Allocation", index=False)
        for sheet in writer.book:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
    return output.getvalue()
