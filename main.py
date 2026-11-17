"""Entry point.

CPU and motherboard temperatures live behind MSR registers and the SuperIO
chip, which PawnIO only exposes to administrators. The app therefore relaunches
itself elevated once; if the user declines, it runs anyway with the readings
that do not need the driver.
"""

from __future__ import annotations

import sys


def main() -> None:
    from hwmon.elevate import is_admin, relaunch_elevated

    if not is_admin():
        if relaunch_elevated():
            # The elevated copy takes over; this one exits quietly.
            return

    from hwmon.app import main as run_app
    run_app()


if __name__ == "__main__":
    main()
