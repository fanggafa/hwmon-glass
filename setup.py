"""First-run setup: install the Python packages and the sensor runtime."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")

# (import name, distribution name) — used only to detect what is missing.
REQUIRED = [
    ("psutil", "psutil"),
    ("PIL", "Pillow"),
    ("clr", "pythonnet"),
    ("pystray", "pystray"),
]


def missing() -> list[str]:
    out = []
    for module, package in REQUIRED:
        try:
            importlib.import_module(module)
        except Exception:
            out.append(package)
    return out


def pip_install(packages: list[str]) -> bool:
    """Installs the pinned versions from requirements.txt.

    Installing by bare package name would fetch the newest Pillow, which adds
    several compiled plugins and makes the bundled executable noticeably larger
    than a build against the pinned version.
    """
    print("installing:", ", ".join(packages))
    try:
        if os.path.exists(REQUIREMENTS):
            rc = subprocess.call(
                [sys.executable, "-m", "pip", "install", "--quiet", "-r", REQUIREMENTS])
        else:
            rc = subprocess.call([sys.executable, "-m", "pip", "install", "--quiet"] + packages)
        return rc == 0
    except Exception as exc:
        print("pip failed:", exc)
        return False


def main() -> int:
    gaps = missing()
    if gaps:
        if not pip_install(gaps):
            print("\nCould not install dependencies automatically.")
            print("Run: pip install " + " ".join(gaps))
            return 1

    import fetch_deps
    if not fetch_deps.fetch():
        print("\nCould not download the sensor runtime.")
        print("Run: python fetch_deps.py")
        return 1

    print("setup complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
