"""Pure-logic tests: no Windows APIs, so they run on any CI runner."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_formatters():
    from hwmon import render as R

    assert R.fmt_pct(None) == "--"
    assert R.fmt_pct(7.77) == "7.8%"
    assert R.fmt_pct(100.0) == "100.0%"

    assert R.fmt_temp(None) == "--"
    assert R.fmt_temp(41.4) == "41°"

    # rates switch units at the right boundaries
    assert R.fmt_rate(0) == "0.0 KB/s"
    assert R.fmt_rate(1024) == "1.0 KB/s"
    assert R.fmt_rate(1024 * 1024) == "1.0 MB/s"
    assert R.fmt_rate(1024 ** 3) == "1.00 GB/s"
    assert R.fmt_rate(-5) == "0.0 KB/s"


def test_uptime():
    from hwmon.render import fmt_uptime

    assert fmt_uptime(0.5) == "30分钟"
    assert fmt_uptime(5) == "5小时"
    assert fmt_uptime(24) == "1天0小时"
    assert fmt_uptime(80.6) == "3天8小时"


def test_load_words():
    from hwmon.render import load_word, score_word

    assert load_word(None) == "未知"
    assert load_word(5) == "空闲"
    assert load_word(30) == "轻载"
    assert load_word(60) == "中载"
    assert load_word(90) == "重载"

    assert score_word(95) == "运行良好"
    assert score_word(80) == "状态正常"
    assert score_word(65) == "略有压力"
    assert score_word(30) == "需要留意"


def test_health_score():
    from hwmon.sampler import Snapshot, compute_score

    # an idle machine with no readings available scores full marks:
    # dimensions the box cannot report must not cost anything
    idle = Snapshot()
    assert compute_score(idle) == 100

    # heavy load and high temperature cost points
    busy = Snapshot(cpu_load=100, ram_load=95, cpu_temp=90)
    assert compute_score(busy) < 70

    # the floor is 1, never 0 or negative
    worst = Snapshot(cpu_load=100, ram_load=100, gpu_load=100, cpu_temp=110)
    assert 1 <= compute_score(worst) <= 100

    # a nearly full disk is penalised
    full = Snapshot(disk_free_gb=5, disk_total_gb=500)
    assert compute_score(full) < 100


def test_cpu_naming():
    from hwmon.hardware import friendly_cpu, cn_num, brand_of

    assert cn_num(12) == "十二"
    assert cn_num(10) == "十"
    assert cn_num(6) == "六"

    out = friendly_cpu("12th Gen Intel(R) Core(TM) i5-12600KF", 10)
    assert "英特尔" in out and "十二代" in out and "i5-12600KF" in out

    amd = friendly_cpu("AMD Ryzen 7 6800H with Radeon Graphics", 8)
    assert amd.startswith("AMD")

    assert brand_of("ASUSTeK COMPUTER INC.") == "华硕"
    assert brand_of("Micro-Star International") == "微星"
    assert brand_of("Gigabyte Technology") == "技嘉"
    assert brand_of("SomeOther") == "SomeOther"


def test_temp_color_thresholds():
    from hwmon.render import temp_color, ACCENT_GREEN, ACCENT_YELLOW, ACCENT_ORANGE, ACCENT_RED

    assert temp_color(None) != ACCENT_GREEN
    assert temp_color(40) == ACCENT_GREEN
    assert temp_color(60) == ACCENT_YELLOW
    assert temp_color(75) == ACCENT_ORANGE
    assert temp_color(95) == ACCENT_RED


def test_history_ring():
    from hwmon.render import History

    h = History(4)
    for v in (1, 2, 3, 4, 5):
        h.push(v)
    # only the last four survive, oldest first
    assert h.values() == [2, 3, 4, 5]
    assert h.capacity == 4


def test_hit_testing_offset():
    """Hit boxes are in content space; the window adds the shadow margin."""
    from hwmon import render as R
    from hwmon.panel import Panel

    p = Panel(scale=1.0)
    p.hits = {"gear": (100, 20, 30, 30)}

    assert p.hit_offset == R.SHADOW_MARGIN

    off = p.hit_offset
    # a click exactly on the button (in window coords) hits it
    assert p.hover_at(110 + off, 30 + off) == "gear"
    # without the offset the same point would miss
    assert p.hover_at(110, 30) == ""
    # far away misses
    assert p.hover_at(500 + off, 500 + off) == ""


def test_panel_geometry_grows_with_scale():
    from hwmon.panel import Panel

    small = Panel(scale=1.0)
    large = Panel(scale=1.5)
    sw, sh = small.body_size()
    lw, lh = large.body_size()
    assert lw > sw and lh > sh
    # scaling is clamped to a sane range
    assert Panel(scale=0.1).scale == 1.0
    assert Panel(scale=9.9).scale == 3.0
