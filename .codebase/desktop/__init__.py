"""OS-level controller package. Platform-neutral core only. No network."""

from .protocol import ok, fail
from .state import current_frame, set_frame, clear_frame
from .move import duration as move_duration
from .move import points as move_points

__all__ = ["ok", "fail", "current_frame", "set_frame", "clear_frame", "move_points", "move_duration"]
