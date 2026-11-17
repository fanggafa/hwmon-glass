"""First-run setup: install the Python packages and the sensor runtime."""

from __future__ import annotations

import importlib
import subprocess
import sys

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
    print("installing:", ", ".join(packages))
    try:
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
