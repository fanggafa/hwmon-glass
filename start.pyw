"""Double-click launcher: starts the monitor without a console window."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hwmon.elevate import is_admin, relaunch_elevated  # noqa: E402


def main() -> None:
    # CPU and motherboard temperatures need MSR/SuperIO access, which PawnIO
    # only grants to administrators. Ask once, then run either way.
    if not is_admin():
        if relaunch_elevated():
            return

    from hwmon.app import main as run
    run()


if __name__ == "__main__":
    main()
