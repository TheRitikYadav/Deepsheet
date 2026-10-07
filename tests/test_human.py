import random

from autodialer.human import Humanizer
from autodialer.ui import Bounds


def test_points_stay_inside_key_and_vary():
    h = Humanizer(rng=random.Random(1))
    b = Bounds(100, 200, 400, 360)
    pts = [h.point_in(b) for _ in range(500)]
    assert all(b.left <= x < b.right and b.top <= y < b.bottom for x, y in pts)
    assert len(set(pts)) > 100           # not always the same pixel
    assert b.center not in pts or len(set(pts)) > 1


def test_timing_ranges():
    h = Humanizer(rng=random.Random(2))
    gaps = [h.key_gap(i) for i in range(300)]
    assert min(gaps) >= h.p.key_gap_min
    assert max(gaps) <= h.p.key_gap_max + h.p.group_pause[1]
    assert len({round(g, 3) for g in gaps}) > 100
    durs = [h.press_duration_ms() for _ in range(100)]
    assert all(h.p.press_ms[0] <= d <= h.p.press_ms[1] for d in durs)
