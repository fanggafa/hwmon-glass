"""Fetches the LibreHardwareMonitor runtime into lib/.

Those assemblies are third-party binaries (MPL-2.0), so they are downloaded on
first run rather than committed to the repository.
"""

from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile

VERSION = "0.9.6"
URL = (f"https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/"
       f"releases/download/v{VERSION}/LibreHardwareMonitor.zip")

WANTED = [
    "LibreHardwareMonitorLib.dll",
    "HidSharp.dll",
    "RAMSPDToolkit-NDD.dll",
    "DiskInfoToolkit.dll",
    "BlackSharp.Core.dll",
    "System.Management.dll",
    "System.Memory.dll",
    "System.Threading.AccessControl.dll",
    "System.Security.AccessControl.dll",
    "System.Security.Principal.Windows.dll",
    "System.Buffers.dll",
    "System.Numerics.Vectors.dll",
    "System.Runtime.CompilerServices.Unsafe.dll",
    "System.Text.Json.dll",
    "System.Text.Encodings.Web.dll",
    "System.Threading.Tasks.Extensions.dll",
    "Microsoft.Bcl.AsyncInterfaces.dll",
    "Microsoft.Bcl.HashCode.dll",
]

ROOT = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(ROOT, "lib")


def have_all() -> bool:
    return all(os.path.exists(os.path.join(LIB, n)) for n in WANTED if n != "System.Management.dll")


def fetch(force: bool = False) -> bool:
    os.makedirs(LIB, exist_ok=True)
    if have_all() and not force:
        return True

    print(f"downloading LibreHardwareMonitor {VERSION} ...")
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=120).read()
    except Exception as e:
        print(f"download failed: {e}")
        return False

    count = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            base = os.path.basename(name)
            if base in WANTED and "/" not in name:
                with open(os.path.join(LIB, base), "wb") as f:
                    f.write(z.read(name))
                count += 1

    print(f"extracted {count} assemblies into lib/")
    return count > 0


if __name__ == "__main__":
    ok = fetch("--force" in sys.argv)
    sys.exit(0 if ok else 1)
