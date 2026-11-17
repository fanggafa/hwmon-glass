"""Renders one panel frame to PNG - used to verify the look without a window."""

from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from hwmon.panel import Panel
from hwmon.sampler import Sampler
from hwmon import hardware


def main():
    scale = 1.0
    if len(sys.argv) > 1:
        scale = float(sys.argv[1])

    sampler = Sampler()
    panel = Panel(scale=scale)
    panel.info = hardware.collect()

    # Let the rate counters settle (they need two reads).
    time.sleep(1.4)
    for _ in range(24):
        snap = sampler.sample()
        panel.update(snap)
        time.sleep(0.18)

    img = panel.render()
    out = "panel_render.png"
    img.save(out)
    print(f"saved {out} {img.width}x{img.height}")

    s = panel.snap
    if s:
        print(f"cpu={s.cpu_load} clock={s.cpu_clock_ghz} gpu={s.gpu_load} "
              f"vram={s.gpu_mem_used_mb} ram={s.ram_load} score={s.score}")
        for p in s.processes:
            print("  ", p)


if __name__ == "__main__":
    main()
