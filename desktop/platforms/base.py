"""Platform adapter contract. Backends implement these methods or raise
CapabilityError for unsupported operations. FocusError stops all input.
"""

from typing import Any, Callable, Dict, Optional, Tuple


class CapabilityError(RuntimeError):
    """The backend does not support this operation on this platform."""

    def __init__(self, capability: str, message: str):
        super().__init__(message)
        self.capability = capability


class FocusError(RuntimeError):
    """Requested focus could not be verified. No input may be sent."""


class InputCancelled(RuntimeError):
    """An adapter stopped cleanly between input primitives."""

    def __init__(self, operation: str, completed: int, total: int):
        super().__init__(f"{operation} cancelled after {completed} of {total} primitives")
        self.operation = operation
        self.completed = completed
        self.total = total


CancellationProbe = Optional[Callable[[], bool]]


class Backend:
    """Platform-neutral adapter interface. One implementation per OS.

    Required (all platforms): screen_size, active_window, cursor_position,
    capture_region, move_path, click, drag, scroll, type_text, hotkey, press,
    launch, focus_app, release_all, trusted, backend_name.
    Optional (raise CapabilityError): list_apps, list_windows, focused_element.
    """

    def backend_name(self) -> str:
        raise NotImplementedError

    def app_matches(self, requested: str, actual: str) -> bool:
        """Platform-neutral default; platform adapters may refine names."""
        return requested.strip().casefold() == actual.strip().casefold()

    def trusted(self) -> bool:
        raise NotImplementedError

    def helper_available(self) -> bool:
        raise CapabilityError("helper", "native helper status is unavailable")

    def screen_recording_authorized(self) -> bool:
        raise CapabilityError(
            "screen_recording", "screen recording status is unavailable"
        )

    def screen_size(self) -> Dict[str, int]:
        raise NotImplementedError

    def display_layout(self) -> Dict[str, Any]:
        """Return the input-coordinate layout, including scale and rotation.

        The conservative default is one unscaled, unrotated display. Native
        adapters should override this when the OS exposes richer metadata.
        """
        screen = self.screen_size()
        left = screen.get("left", 0)
        top = screen.get("top", 0)
        width = screen["width"]
        height = screen["height"]
        return {
            "origin": [left, top],
            "width": width,
            "height": height,
            "displays": [
                {
                    "id": "default",
                    "origin": [left, top],
                    "width": width,
                    "height": height,
                    "scale": [1.0, 1.0],
                    "rotation": 0.0,
                }
            ],
        }

    def active_window(self) -> str:
        raise NotImplementedError

    def cursor_position(self) -> Tuple[int, int]:
        raise NotImplementedError

    def capture_region(self, x: int, y: int, w: int, h: int):
        raise NotImplementedError

    def move_path(
        self, points, total_secs: float, cancelled: CancellationProbe = None
    ) -> None:
        raise NotImplementedError

    def click(
        self, x: int, y: int, button: str = "left", double: bool = False,
        cancelled: CancellationProbe = None,
    ) -> None:
        raise NotImplementedError

    def drag(self, frm, to, path, cancelled: CancellationProbe = None) -> None:
        raise NotImplementedError

    def scroll(
        self, direction: str, amount: int, cancelled: CancellationProbe = None
    ) -> None:
        raise NotImplementedError

    def type_text(
        self, text: str, gaps, cancelled: CancellationProbe = None
    ) -> int:
        raise NotImplementedError

    def hotkey(self, keys: str, cancelled: CancellationProbe = None) -> None:
        raise NotImplementedError

    def press(self, key: str, cancelled: CancellationProbe = None) -> None:
        raise NotImplementedError

    def launch(self, app: str) -> str:
        raise NotImplementedError

    def focus_app(self, app: str, timeout: float = 5.0) -> str:
        raise NotImplementedError

    def release_all(self) -> None:
        """Release any held keys/buttons/drag state. Called on every failure path."""
        raise NotImplementedError

    def list_apps(self):
        raise CapabilityError("list_apps", "list_apps is not supported by this backend")

    def list_windows(self, app: str = ""):
        raise CapabilityError("list_windows", "list_windows is not supported by this backend")

    def focused_element(self):
        raise CapabilityError("focused_element", "focused element lookup not supported here")

    def element_at(self, x: int, y: int):
        raise CapabilityError("element_at", "coordinate element lookup not supported here")
