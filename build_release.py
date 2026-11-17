"""One-step release build.

Downloads the LibreHardwareMonitor runtime and the PawnIO installer, then packs
everything into a single windowed executable. Both third-party binaries are
fetched rather than committed, so the repository stays source-only.
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")
PAWNIO_URL = ("https://github.com/namazso/PawnIO.Setup/releases/latest/download/"
              "PawnIO_setup.exe")


def fetch_pawnio() -> bool:
    os.makedirs(ASSETS, exist_ok=True)
    target = os.path.join(ASSETS, "PawnIO_setup.exe")
    if os.path.exists(target) and os.path.getsize(target) > 1_000_000:
        print("PawnIO installer already present")
        return True

    print("downloading PawnIO installer...")
    try:
        req = urllib.request.Request(PAWNIO_URL, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=120).read()
        with open(target, "wb") as f:
            f.write(data)
        print(f"  {len(data) / 1024 / 1024:.1f} MB")
        return True
    except Exception as exc:
        print(f"  failed: {exc}")
        return False


def main() -> int:
    os.chdir(ROOT)

    import fetch_deps
    if not fetch_deps.fetch():
        print("could not obtain the sensor runtime")
        return 1

    if not fetch_pawnio():
        print("building without the bundled driver installer")

    print("running PyInstaller...")
    rc = subprocess.call([sys.executable, "-m", "PyInstaller", "--noconfirm",
                          "--clean", "LiquidGlassMon.spec"])
    if rc != 0:
        print("PyInstaller failed")
        return rc

    exe = os.path.join(ROOT, "dist", "LiquidGlassMon.exe")
    if os.path.exists(exe):
        size = os.path.getsize(exe) / 1024 / 1024
        print(f"\nbuilt: dist/LiquidGlassMon.exe ({size:.1f} MB)")
        return 0

    print("executable not found after build")
    return 1


if __name__ == "__main__":
    sys.exit(main())
