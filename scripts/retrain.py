#!/usr/bin/env python
"""Retrain all model bundles and stage them under ``models/`` for commit.

Run this on the KR host (real KOSPI data is reachable there), then commit + push
so Railway redeploys with the fresh bundles baked into the image. See
``docs/RETRAIN.md``.

Examples::

    python scripts/retrain.py
    python scripts/retrain.py --horizons 5,20 --model-version v2026-06
    python scripts/retrain.py --no-sync          # train only, don't touch models/

This forwards all arguments to ``python -m kospi_flow.cli retrain``.
"""

import sys

from kospi_flow.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["retrain", *sys.argv[1:]]))
