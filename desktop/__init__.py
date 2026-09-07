"""OS-level controller package. Platform-neutral core only. No network."""

from .protocol import ok, fail
from .move import duration as move_duration
from .move import points as move_points
from ._version import __version__

__all__ = ["ok", "fail", "move_points", "move_duration", "__version__"]
