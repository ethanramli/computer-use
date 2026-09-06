"""One bounded screenshot/frame owner with capacity-one semantics."""

import base64
import copy
import math
import os
import stat
import struct
import tempfile
import threading
import zlib
from typing import Any, Dict, Optional

_SEQ = 0
_SEQ_LOCK = threading.Lock()
_DELIVERIES = {"metadata", "base64", "path"}


def _next_id() -> str:
    global _SEQ
    with _SEQ_LOCK:
        _SEQ += 1
        return f"frame-{_SEQ}"


class FrameTooLarge(Exception):
    """The requested capture cannot fit the configured total byte budget."""


def _png_bound(width: int, height: int) -> int:
    scanlines = height * (1 + width * 3)
    zlib_bound = (
        scanlines
        + (scanlines >> 12)
        + (scanlines >> 14)
        + (scanlines >> 25)
        + 13
    )
    return zlib_bound + 57


def capture_budget(
    width: int,
    height: int,
    delivery: str,
    result_metadata_bytes: int = 256,
) -> Dict[str, int]:
    """Worst-case bytes held while capturing and producing one result."""
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
    ):
        raise ValueError("capture width/height must be positive integers")
    if delivery not in _DELIVERIES:
        raise ValueError(f"unknown screenshot delivery: {delivery}")
    if (
        isinstance(result_metadata_bytes, bool)
        or not isinstance(result_metadata_bytes, int)
        or result_metadata_bytes < 0
    ):
        raise ValueError("result_metadata_bytes must be a nonnegative integer")
    pixels = width * height
    # MSS owns a 4-byte capture buffer while materializing our packed RGB
    # copy. Both allocations must fit before capture begins.
    raw = pixels * 4
    normalized = pixels * 3
    encoded = 0 if delivery == "metadata" else _png_bound(width, height)
    # PNG construction can transiently hold compressed data and finalized
    # bytes together. Count those working copies as part of the same limit.
    encoding_working = 0 if delivery == "metadata" else encoded * 2
    encoded_b64 = 0
    json_result = result_metadata_bytes
    if delivery == "base64":
        encoded_b64 = 4 * ((encoded + 2) // 3)
        json_result += encoded_b64
    elif delivery == "path":
        json_result += 1024
    return {
        "raw": raw,
        "normalized": normalized,
        "encoded": encoded,
        "encoding_working": encoding_working,
        "base64": encoded_b64,
        "json_result": json_result,
        "total": (
            raw + normalized + encoded + encoding_working
            + encoded_b64 + json_result
        ),
    }


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(
        ">I", zlib.crc32(body) & 0xFFFFFFFF
    )


def encode_png(rgb: bytes, width: int, height: int) -> bytes:
    """Encode packed RGB bytes without delegating ownership to an adapter."""
    expected = width * height * 3
    if not isinstance(rgb, bytes) or len(rgb) != expected:
        raise ValueError(
            f"capture returned {len(rgb) if isinstance(rgb, bytes) else 'non-bytes'} "
            f"RGB bytes; expected {expected}"
        )
    stride = width * 3
    scanlines = b"".join(
        b"\0" + rgb[offset : offset + stride]
        for offset in range(0, expected, stride)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(scanlines))
        + _chunk(b"IEND", b"")
    )


def point_on_display(layout: Dict[str, Any], x: int, y: int) -> bool:
    for display in layout.get("displays", []):
        origin = display.get("origin", [])
        if not isinstance(origin, (list, tuple)) or len(origin) != 2:
            continue
        left, top = origin
        width, height = display.get("width"), display.get("height")
        if (
            all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in (left, top, width, height)
            )
            and width > 0
            and height > 0
            and left <= x < left + width
            and top <= y < top + height
        ):
            return True
    return False


def validate_layout(layout: Any) -> None:
    """Reject incomplete or internally inconsistent coordinate metadata."""
    if not isinstance(layout, dict):
        raise ValueError("display layout must be an object")
    origin = layout.get("origin")
    displays = layout.get("displays")
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise ValueError("display layout origin must contain two integers")
    bounds = (origin[0], origin[1], layout.get("width"), layout.get("height"))
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in bounds):
        raise ValueError("display layout bounds must be integers")
    if bounds[2] <= 0 or bounds[3] <= 0:
        raise ValueError("display layout width/height must be positive")
    if not isinstance(displays, list) or not displays:
        raise ValueError("display layout must contain at least one display")

    lefts = []
    tops = []
    rights = []
    bottoms = []
    for display in displays:
        if not isinstance(display, dict) or "id" not in display:
            raise ValueError("each display must be an object with an id")
        item_origin = display.get("origin")
        if not isinstance(item_origin, (list, tuple)) or len(item_origin) != 2:
            raise ValueError("each display origin must contain two integers")
        values = (
            item_origin[0], item_origin[1],
            display.get("width"), display.get("height"),
        )
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
            raise ValueError("display bounds must be integers")
        if values[2] <= 0 or values[3] <= 0:
            raise ValueError("display width/height must be positive")
        scale = display.get("scale")
        if not isinstance(scale, (list, tuple)) or len(scale) != 2 or not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
            for value in scale
        ):
            raise ValueError("each display needs a positive finite x/y scale")
        rotation = display.get("rotation")
        if (
            not isinstance(rotation, (int, float))
            or isinstance(rotation, bool)
            or not math.isfinite(rotation)
        ):
            raise ValueError("each display needs a finite rotation")
        lefts.append(values[0])
        tops.append(values[1])
        rights.append(values[0] + values[2])
        bottoms.append(values[1] + values[3])
    expected = (min(lefts), min(tops), max(rights) - min(lefts), max(bottoms) - min(tops))
    if bounds != expected:
        raise ValueError("display layout bounds do not match its displays")


class FrameStore:
    """Owns one current frame and, when requested, one private stable PNG."""

    def __init__(self, max_bytes: int):
        if (
            isinstance(max_bytes, bool)
            or not isinstance(max_bytes, int)
            or max_bytes <= 0
        ):
            raise ValueError("max_bytes must be a positive integer")
        self._max_bytes = max_bytes
        self._frame: Optional[Dict[str, Any]] = None
        self._runtime_dir: Optional[str] = None
        self._path: Optional[str] = None
        self._lock = threading.Lock()

    def preflight_capture(
        self,
        width: int,
        height: int,
        delivery: str,
        result_metadata_bytes: int = 256,
    ) -> Dict[str, int]:
        budget = capture_budget(
            width, height, delivery, result_metadata_bytes
        )
        if budget["total"] > self._max_bytes:
            raise FrameTooLarge(
                f"frame too_large: needs at most {budget['total']} bytes; "
                f"limit is {self._max_bytes}"
            )
        return budget

    def store_rgb(
        self,
        raw: bytes,
        width: int,
        height: int,
        layout: Dict[str, Any],
        region: tuple,
        delivery: str,
        result_metadata_bytes: int = 256,
        active_window: str = "",
    ) -> Dict[str, Any]:
        self.preflight_capture(
            width, height, delivery, result_metadata_bytes
        )
        expected = width * height * 3
        if not isinstance(raw, bytes) or len(raw) != expected:
            raise ValueError(
                f"capture returned {len(raw) if isinstance(raw, bytes) else 'non-bytes'} "
                f"RGB bytes; expected {expected}"
            )

        png = encode_png(raw, width, height) if delivery != "metadata" else None
        image_b64 = (
            base64.b64encode(png).decode("ascii")
            if delivery == "base64" and png is not None
            else None
        )
        actual_total = len(raw) + (len(png) if png is not None else 0)
        if image_b64 is not None:
            actual_total += len(image_b64.encode("ascii"))
        actual_total += result_metadata_bytes
        if delivery == "path":
            actual_total += 1024
        if actual_total > self._max_bytes:
            raise FrameTooLarge(
                f"frame too_large: result uses {actual_total} bytes; "
                f"limit is {self._max_bytes}"
            )

        with self._lock:
            frame = {
                "id": _next_id(),
                "layout": copy.deepcopy(layout),
                "region": tuple(region),
                "active_window": active_window,
            }
            if delivery == "path":
                assert png is not None
                frame["path"] = self._replace_path(png)
            else:
                self._drop_path()
            if image_b64 is not None:
                frame["image_b64"] = image_b64
            self._frame = frame
            return frame

    def latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._frame

    def get(self, frame_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            frame = self._frame
            return frame if frame and frame["id"] == frame_id else None

    def count(self) -> int:
        with self._lock:
            return 1 if self._frame else 0

    def fresh(self, frame_id: str, layout: Dict[str, Any]) -> bool:
        frame = self.get(frame_id)
        return bool(frame and frame["layout"] == layout)

    def authorizes(self, frame_id: str, layout: Dict[str, Any], points) -> bool:
        """Authorize current-layout points inside the capture and a display."""
        frame = self.get(frame_id)
        if not frame or frame["layout"] != layout:
            return False
        left, top, width, height = frame["region"]
        return all(
            left <= x < left + width
            and top <= y < top + height
            and point_on_display(layout, x, y)
            for x, y in points
        )

    def _replace_path(self, png: bytes) -> str:
        if self._runtime_dir is None:
            self._runtime_dir = tempfile.mkdtemp(
                prefix=f"computer-automation-{os.getuid()}-"
            )
            os.chmod(self._runtime_dir, 0o700)
        target = os.path.join(self._runtime_dir, "current.png")
        fd, temporary = tempfile.mkstemp(
            prefix=".current-", suffix=".tmp", dir=self._runtime_dir
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as file:
                fd = -1
                file.write(png)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        target_stat = os.lstat(target)
        if not stat.S_ISREG(target_stat.st_mode) or target_stat.st_uid != os.getuid():
            raise RuntimeError("screenshot path is not a regular owner file")
        self._path = target
        return target

    def _drop_path(self) -> None:
        if self._path:
            try:
                os.unlink(self._path)
            except FileNotFoundError:
                pass
            self._path = None

    def clear(self) -> None:
        with self._lock:
            self._drop_path()
            self._frame = None
            if self._runtime_dir:
                try:
                    os.rmdir(self._runtime_dir)
                except FileNotFoundError:
                    pass
                self._runtime_dir = None

    close = clear

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
