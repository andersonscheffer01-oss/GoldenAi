"""Chronological walk-forward and untouched OOS planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    index: int
    train: tuple
    test: tuple


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    rows: tuple
    windows: tuple[WalkForwardWindow, ...]
    oos: tuple


def build_walk_forward_plan(rows, train_size: int, test_size: int,
                            step: int | None = None, oos_size: int = 0) -> WalkForwardPlan:
    rows = tuple(rows)
    if train_size <= 0 or test_size <= 0:
        raise ValueError("WINDOW_SIZE_INVALID")
    step = test_size if step is None else int(step)
    if step <= 0 or oos_size < 0 or len(rows) <= train_size + test_size + oos_size - 1:
        raise ValueError("WINDOW_CONFIGURATION_INVALID")
    cutoff = len(rows) - oos_size if oos_size else len(rows)
    windows = []
    start = 0
    index = 0
    while start + train_size + test_size <= cutoff:
        train = rows[start:start + train_size]
        test_start = start + train_size
        test = rows[test_start:test_start + test_size]
        windows.append(WalkForwardWindow(index, tuple(train), tuple(test)))
        start += step
        index += 1
    oos = tuple(rows[-oos_size:]) if oos_size else ()
    if oos_size and not windows:
        raise ValueError("NO_PRE_OOS_WINDOW")
    return WalkForwardPlan(rows, tuple(windows), oos)


def run_walk_forward(plan: WalkForwardPlan, evaluator) -> dict:
    if not callable(evaluator):
        raise TypeError("EVALUATOR_REQUIRED")
    results = []
    for window in plan.windows:
        results.append({
            "index": window.index,
            "train_count": len(window.train),
            "test_count": len(window.test),
            "evaluation": evaluator(window.train, window.test, False),
        })
    oos_result = None
    if plan.oos:
        oos_train = plan.rows[:-len(plan.oos)]
        oos_result = {
            "train_count": len(oos_train),
            "test_count": len(plan.oos),
            "is_oos": True,
            "evaluation": evaluator(tuple(oos_train), plan.oos, True),
        }
    return {
        "status": "COMPUTED",
        "windows": results,
        "oos": oos_result,
        "oos_reserved": bool(plan.oos),
    }


__all__ = ["WalkForwardPlan", "WalkForwardWindow", "build_walk_forward_plan", "run_walk_forward"]

