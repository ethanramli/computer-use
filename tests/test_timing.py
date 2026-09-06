"""Timing modes: human (accepted Bezier/Fitts + measured gaps),
compatibility (fixed measured intervals), native (no artificial pacing).
Negative/invalid durations clamp to zero. Exact landing preserved.
"""

import pytest

from desktop.timing import TimingMode, gaps_for, movement_seconds


def test_native_mode_has_no_delays():
    assert list(gaps_for("native", "hello")) == [0.0] * 5


def test_human_mode_uses_measured_distribution():
    g = list(gaps_for("human", "hello"))
    assert len(g) == 5
    assert all(0.0 <= x <= 0.4 for x in g)


def test_compat_mode_uses_fixed_interval():
    g = list(gaps_for("compatibility", "abc"))
    assert g == [TimingMode.COMPAT_GAP_S] * 3


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        gaps_for("warp", "abc")


def test_movement_seconds_clamps_negative():
    # tiny distances used to go negative from the log; must clamp to >= 0
    assert movement_seconds("native", 0, 0, 1, 0) == 0.0
    assert movement_seconds("human", 0, 0, 0, 0) == 0.0


def test_movement_seconds_native_is_zero():
    assert movement_seconds("native", 0, 0, 500, 500) == 0.0


def test_movement_seconds_human_matches_fitts():
    d = movement_seconds("human", 0, 0, 1000, 0)
    assert 0.5 < d < 3.0


def test_compat_between_human_and_native():
    h = movement_seconds("human", 0, 0, 500, 500)
    c = movement_seconds("compatibility", 0, 0, 500, 500)
    n = movement_seconds("native", 0, 0, 500, 500)
    assert n <= c <= h
