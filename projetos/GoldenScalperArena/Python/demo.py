"""Generate a clearly synthetic end-to-end Arena report for panel QA."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from golden_scalper_arena.contracts import Bar, MarketSnapshot, SymbolSpec, Tick
from golden_scalper_arena.validation_pipeline import run_validation_pipeline, write_report


def build_demo_snapshots(count: int = 120) -> tuple[MarketSnapshot, ...]:
    base_time = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)
    spec = SymbolSpec(
        symbol="XAUUSD", digits=2, point=0.01, tick_size=0.01,
        tick_value=1.0, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
    )
    closes = []
    price = 2300.0
    # Alternating deterministic regimes exercise trend, pullback, rejection and
    # sweep rules without claiming that the fixture represents a market history.
    regime_steps = (0.18, 0.10, -0.16, -0.08, 0.22, -0.20)
    for index in range(1, count + 1):
        step = regime_steps[((index - 1) // 10) % len(regime_steps)]
        if index % 7 == 0:
            step *= -0.25
        price += step
        closes.append(round(price, 4))

    m1 = []
    for index, close in enumerate(closes, 1):
        previous = closes[index - 2] if index > 1 else close - 0.05
        open_ = previous
        high = max(open_, close) + 0.10
        low = min(open_, close) - 0.10
        if index % 11 == 0:
            low = min(open_, close) - 0.45
            close = round(max(close, open_) + 0.04, 4)
            closes[index - 1] = close
        if index % 17 == 0:
            high = max(open_, close) + 0.45
            close = round(min(close, open_) - 0.04, 4)
            closes[index - 1] = close
        m1.append(Bar(
            symbol="XAUUSD", timeframe="M1", event_index=index,
            close_time=base_time + timedelta(seconds=index),
            open=open_, high=high, low=low, close=close,
        ))

    h1 = []
    for end in range(5, count + 1, 5):
        block = m1[end - 5:end]
        h1.append(Bar(
            symbol="XAUUSD", timeframe="H1", event_index=end,
            close_time=block[-1].close_time,
            open=block[0].open, high=max(row.high for row in block),
            low=min(row.low for row in block), close=block[-1].close,
        ))

    snapshots = []
    for index, row in enumerate(m1, 1):
        bid = closes[index - 1]
        snapshots.append(MarketSnapshot(
            run_id="demo-synthetic-2026-11-07", spec=spec,
            tick=Tick(
                symbol="XAUUSD", event_index=index,
                timestamp=base_time + timedelta(seconds=index),
                bid=bid, ask=bid + 0.08,
            ),
            closed_bars={
                "M1": tuple(m1[:index]),
                "H1": tuple(bar for bar in h1 if bar.event_index <= index),
            },
        ))
    return tuple(snapshots)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="../Data/experiments/latest_report.json")
    parser.add_argument("--count", type=int, default=120)
    args = parser.parse_args(argv)
    report = run_validation_pipeline(
        build_demo_snapshots(args.count), source_kind="DEMO_SYNTHETIC",
        provenance="deterministic fixture generated locally for panel verification",
        paper_session_count=30,
    )
    destination = write_report(report, args.output)
    print(f"REPORT={destination}")
    print(f"SOURCE={report['run']['source_kind']}")
    print(f"SECURITY={report['security']}")
    print("RANKING=" + ",".join(
        f"{row['rank']}:{row['agent']}:{row['metrics']['net_pnl']}"
        for row in report["agents"]
    ))
    print("VALIDATION=" + report["validation"]["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

