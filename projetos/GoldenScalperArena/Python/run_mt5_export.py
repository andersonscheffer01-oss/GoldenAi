"""Run the Arena pipeline over a read-only MT5 FILE_COMMON export."""

from __future__ import annotations

import argparse
from datetime import timedelta, timezone

from golden_scalper_arena.mt5_export import load_mt5_export
from golden_scalper_arena.validation_pipeline import run_validation_pipeline, write_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, help="Folder containing ticks.csv and symbol_spec.csv")
    parser.add_argument("--report", required=True, help="Output JSON consumed by the local panel")
    parser.add_argument("--server-offset-hours", required=True, type=float,
                        help="Confirmed MT5 server offset, e.g. 2 or -3; never guessed")
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args(argv)
    server_timezone = timezone(timedelta(hours=args.server_offset_hours))
    export = load_mt5_export(
        args.directory, server_timezone=server_timezone, expected_symbol=args.symbol,
    )
    report = run_validation_pipeline(
        export.snapshots,
        source_kind="MT5_FILE_COMMON",
        provenance=(
            f"{export.source}; time_authority={export.time_authority}; "
            f"server_offset_hours={args.server_offset_hours}"
        ),
    )
    report["run"]["mt5_export_source"] = str(args.directory)
    report["run"]["time_authority"] = export.time_authority
    destination = write_report(report, args.report)
    print(f"REPORT={destination}")
    print(f"SNAPSHOTS={len(export.snapshots)}")
    print(f"TIME_AUTHORITY={export.time_authority}")
    print(f"EXECUTION_AUTHORITY={export.execution_authority}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

