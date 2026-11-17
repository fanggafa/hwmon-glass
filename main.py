"""Entry point.

CPU and motherboard temperatures live behind MSR registers and the SuperIO
chip, which PawnIO only exposes to administrators. The app therefore relaunches
itself elevated once; if the user declines, it runs anyway with the readings
that do not need the driver.

The single-instance guard matters here: the elevated copy and the original both
start otherwise, and the duplicate tray icon makes every menu item look broken.
"""

from __future__ import annotations


def main() -> None:
    from hwmon.elevate import is_admin, relaunch_elevated
    from hwmon.single import acquire

    # The elevated copy wins the race because it starts slightly later and the
    # original exits first; checking before relaunching keeps the order right.
    if not is_admin():
        if relaunch_elevated():
            return

    if not acquire():
        # Another instance already owns the tray; do nothing and exit quietly.
        return

    from hwmon.app import main as run_app
    run_app()


if __name__ == "__main__":
    main()
