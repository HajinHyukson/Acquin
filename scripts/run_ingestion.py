#!/usr/bin/env python
"""Run a sample ingestion for a date range.

Examples::

    python scripts/run_ingestion.py --start 2021-01-01 --end 2021-03-31

This forwards all arguments to ``python -m kospi_flow.cli ingest``.
"""

import sys

from kospi_flow.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["ingest", *sys.argv[1:]]))
