"""Windows adapter. SendInput + foreground verification; UI Automation later.

Not implemented on this host (no Windows available for live verification).
Every operation raises an explicit structured capability error through
WindowsBackend; nothing silently fakes success.
"""

from .base import Backend, CapabilityError


class WindowsBackend(Backend):
    def backend_name(self) -> str:
        return "windows"

    def _unsupported(self, cap):
        raise CapabilityError(
            cap,
            f"{cap} is not implemented for the Windows backend yet; "
            "requires a Windows host with SendInput support",
        )

    def trusted(self):
        self._unsupported("trusted")

    def screen_size(self):
        self._unsupported("screen_size")

    def active_window(self):
        self._unsupported("active_window")

    def cursor_position(self):
        self._unsupported("cursor_position")

    def capture_region(self, x, y, w, h):
        self._unsupported("capture_region")

    def move_path(self, points, total_secs, cancelled=None):
        self._unsupported("move_path")

    def click(self, x, y, button="left", double=False, cancelled=None):
        self._unsupported("click")

    def drag(self, frm, to, path, cancelled=None):
        self._unsupported("drag")

    def scroll(self, direction, amount, cancelled=None):
        self._unsupported("scroll")

    def type_text(self, text, gaps, cancelled=None):
        self._unsupported("type_text")

    def hotkey(self, keys, cancelled=None):
        self._unsupported("hotkey")

    def press(self, key, cancelled=None):
        self._unsupported("press")

    def launch(self, app):
        self._unsupported("launch")

    def focus_app(self, app, timeout=5.0):
        self._unsupported("focus_app")

    def release_all(self):
        pass  # nothing is ever held
