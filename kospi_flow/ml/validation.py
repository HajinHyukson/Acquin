"""Time-based walk-forward validation (context doc §11.5).

Never random splits: each fold trains on past dates and tests on a strictly
later, contiguous block of dates. An embargo gap (>= horizon) is left between
train and test so forward-looking targets in the training set cannot overlap the
test period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass
class Fold:
    train_dates: list[date]
    test_dates: list[date]


def walk_forward_splits(
    dates: pd.Series,
    n_splits: int = 3,
    embargo: int = 0,
    min_train: int = 30,
    train_window: int | None = None,
) -> list[Fold]:
    """Walk-forward folds over the sorted unique dates.

    ``embargo`` trading dates are dropped between each train block and its test
    block to avoid target leakage (set it to the prediction horizon).

    ``train_window`` caps each fold's train block to its last N dates (rolling
    window); ``None`` keeps the expanding window (all history up to the cut). Set
    it to ``Settings.train_window_days`` so the OOS evaluation reflects how the
    deployed bundle is actually fit (context doc §24.1 / §25 Phase B).
    """

    def _train_start(train_end: int) -> int:
        return 0 if not train_window else max(0, train_end - train_window)

    unique = sorted(pd.Series(dates).dropna().unique())
    n = len(unique)
    if n < min_train + n_splits + embargo + 1:
        # Not enough history for the requested folds; return a single split.
        cut = max(min_train, int(n * 0.7))
        if cut + embargo >= n:
            return []
        return [Fold(unique[_train_start(cut) : cut], unique[cut + embargo :])]

    test_size = max(1, (n - min_train) // (n_splits + 1))
    folds: list[Fold] = []
    for k in range(1, n_splits + 1):
        train_end = min_train + (k - 1) * test_size
        test_start = train_end + embargo
        test_end = test_start + test_size
        if test_start >= n:
            break
        folds.append(
            Fold(
                train_dates=unique[_train_start(train_end) : train_end],
                test_dates=unique[test_start : min(test_end, n)],
            )
        )
    return folds


def split_panel(panel: pd.DataFrame, fold: Fold) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Slice a (date-keyed) panel into train/test frames for a fold."""
    train_set = set(fold.train_dates)
    test_set = set(fold.test_dates)
    train = panel[panel["date"].isin(train_set)]
    test = panel[panel["date"].isin(test_set)]
    return train, test
