"""Frame store: capacity-one metadata, bounded screenshot delivery, no history."""

import os
import stat
from pathlib import Path

import pytest

from desktop.frames import FrameStore, FrameTooLarge


LAYOUT = {
    "origin": [0, 0],
    "width": 800,
    "height": 600,
    "displays": [
        {
            "id": "display-1",
            "origin": [0, 0],
            "width": 800,
            "height": 600,
            "scale": [2.0, 2.0],
            "rotation": 0.0,
        }
    ],
}


def rgb(width=2, height=2, value=0):
    return bytes([value]) * width * height * 3


def test_store_keeps_only_latest_frame():
    fs = FrameStore(max_bytes=10_000_000)
    f1 = fs.store_rgb(rgb(), 2, 2, LAYOUT, (0, 0, 2, 2), "metadata")
    f2 = fs.store_rgb(rgb(value=1), 2, 2, LAYOUT, (0, 0, 2, 2), "metadata")
    assert fs.latest() is f2
    assert fs.count() == 1
    assert f1["id"] != f2["id"]
    # stale frame is gone
    assert fs.get(f1["id"]) is None


def test_store_rejects_oversized_frame():
    fs = FrameStore(max_bytes=10)
    with pytest.raises(FrameTooLarge) as e:
        fs.preflight_capture(2, 2, "base64")
    assert "too_large" in str(e.value)


def test_ten_thousand_replacements_no_growth_no_files():
    fs = FrameStore(max_bytes=10_000_000)
    import threading

    before = threading.active_count()
    for i in range(10_000):
        fs.store_rgb(
            rgb(value=i % 256), 2, 2, LAYOUT, (0, 0, 2, 2), "metadata"
        )
    assert fs.count() == 1
    assert threading.active_count() == before


def test_path_mode_uses_one_private_stable_file_and_close_removes_it():
    fs = FrameStore(max_bytes=10_000_000)
    p1 = fs.store_rgb(rgb(value=1), 2, 2, LAYOUT, (0, 0, 2, 2), "path")["path"]
    first = Path(p1).read_bytes()
    p2 = fs.store_rgb(rgb(value=2), 2, 2, LAYOUT, (0, 0, 2, 2), "path")["path"]
    assert p1 == p2
    assert fs.count() == 1
    assert os.path.exists(p2)
    assert Path(p2).read_bytes() != first
    assert stat.S_IMODE(os.stat(p2).st_mode) == 0o600
    parent = os.path.dirname(p2)
    assert stat.S_IMODE(os.stat(parent).st_mode) == 0o700
    fs.close()
    assert not os.path.exists(p2)
    assert not os.path.exists(parent)


def test_stale_frame_id_rejected():
    fs = FrameStore(max_bytes=1000)
    f1 = fs.store_rgb(rgb(), 2, 2, LAYOUT, (0, 0, 2, 2), "metadata")
    fs.store_rgb(rgb(value=1), 2, 2, LAYOUT, (0, 0, 2, 2), "metadata")
    assert fs.fresh(f1["id"], layout=LAYOUT) is False
    f2 = fs.latest()
    assert fs.fresh(f2["id"], layout=LAYOUT) is True
    changed = {**LAYOUT, "displays": [{**LAYOUT["displays"][0], "rotation": 90.0}]}
    assert fs.fresh(f2["id"], layout=changed) is False


def test_base64_delivery_is_encoded_once_and_is_a_png():
    fs = FrameStore(max_bytes=10_000_000)
    frame = fs.store_rgb(rgb(), 2, 2, LAYOUT, (0, 0, 2, 2), "base64")

    import base64

    assert base64.b64decode(frame["image_b64"]).startswith(b"\x89PNG\r\n\x1a\n")
    assert "raw" not in frame


def test_authorization_rejects_display_gaps_even_inside_virtual_bounds():
    layout = {
        "origin": [0, 0],
        "width": 300,
        "height": 100,
        "displays": [
            {"id": "a", "origin": [0, 0], "width": 100, "height": 100,
             "scale": [1.0, 1.0], "rotation": 0.0},
            {"id": "b", "origin": [200, 0], "width": 100, "height": 100,
             "scale": [1.0, 1.0], "rotation": 0.0},
        ],
    }
    fs = FrameStore(max_bytes=10_000_000)
    frame = fs.store_rgb(rgb(), 2, 2, layout, (0, 0, 300, 100), "metadata")

    assert fs.authorizes(frame["id"], layout, [(50, 50)]) is True
    assert fs.authorizes(frame["id"], layout, [(150, 50)]) is False
