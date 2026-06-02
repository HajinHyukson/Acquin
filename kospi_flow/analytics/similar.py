"""Similar-case retrieval (context doc §9.6).

Given a stock's feature history, find the historical dates whose (standardized)
feature vector is closest to a reference date, and report what happened next.
Intentionally simple (nearest-neighbour by Euclidean distance) for the MVP.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def find_similar_cases(
    feature_df: pd.DataFrame,
    feature_cols: list[str],
    outcome: pd.Series,
    reference_index: int | None = None,
    k: int = 10,
) -> list[dict]:
    """Return the ``k`` most similar past dates to ``reference_index``.

    ``feature_df`` must include a ``date`` column and ``feature_cols``.
    ``outcome`` is a forward-return Series aligned to ``feature_df`` rows.
    Only rows strictly before the reference date are eligible (no look-ahead).
    """
    df = feature_df.reset_index(drop=True)
    if reference_index is None:
        reference_index = len(df) - 1
    X = df[feature_cols].to_numpy(dtype=float)
    # Standardize columns; guard against zero-variance.
    mean = np.nanmean(X, axis=0)
    std = np.nanstd(X, axis=0)
    std[std == 0] = 1.0
    Z = (X - mean) / std
    Z = np.nan_to_num(Z, nan=0.0)

    ref = Z[reference_index]
    dist = np.linalg.norm(Z - ref, axis=1)

    eligible = [i for i in range(len(df)) if i < reference_index]
    eligible.sort(key=lambda i: dist[i])
    out: list[dict] = []
    for i in eligible[:k]:
        out.append(
            {
                "date": df.loc[i, "date"].isoformat()
                if hasattr(df.loc[i, "date"], "isoformat")
                else str(df.loc[i, "date"]),
                "distance": float(dist[i]),
                "subsequent_return": (
                    None if pd.isna(outcome.iloc[i]) else float(outcome.iloc[i])
                ),
            }
        )
    return out
