#!/usr/bin/env python
"""Run data validation checks against the configured database.

Forwards to ``python -m kospi_flow.cli validate``. Exits non-zero if any
ERROR-severity issues are found.
"""

import sys

from kospi_flow.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["validate", *sys.argv[1:]]))
