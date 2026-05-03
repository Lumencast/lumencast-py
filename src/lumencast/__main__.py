"""``python -m lumencast`` entry — delegates to the CLI dispatcher."""

from __future__ import annotations

import sys

from lumencast.cli.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
