import argparse
import sys
from pathlib import Path

from .export import excel_export
from .pipeline import refresh
from .providers import DataError, YahooFinanceProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh validated daily equity research data")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--excel", type=Path)
    args = parser.parse_args()
    try:
        frames = refresh(YahooFinanceProvider(), args.data_dir)
        if args.excel:
            args.excel.parent.mkdir(parents=True, exist_ok=True)
            args.excel.write_bytes(excel_export(frames))
        print("Validated refresh complete: " + ", ".join(frames))
        return 0
    except DataError as exc:
        print(f"DATA ERROR: {exc}. No research signals exported.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
