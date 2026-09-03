"""Transient frame state. Keeps only the current screenshot."""

from typing import Optional

_current_frame: Optional[str] = None


def set_frame(path: str) -> str:
    global _current_frame
    _current_frame = path
    return path


def current_frame() -> Optional[str]:
    return _current_frame


def clear_frame() -> None:
    global _current_frame
    _current_frame = None
