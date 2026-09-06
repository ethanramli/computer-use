"""Same contract tests run against every platform adapter.

macOS runs live on this host; Windows/Linux adapters are verified to honor
the contract by raising explicit CapabilityError for every operation rather
than faking success.
"""

import platform

import pytest

from desktop.platforms.base import CapabilityError
from desktop.platforms.linux import LinuxBackend
from desktop.platforms.windows import WindowsBackend

OPERATIONS = [
    ("trusted", ()),
    ("screen_size", ()),
    ("active_window", ()),
    ("cursor_position", ()),
    ("capture_region", (0, 0, 10, 10)),
    ("move_path", ([(0, 0)], 0.1)),
    ("click", (1, 2)),
    ("drag", ((0, 0), (1, 1), [(0, 0)])),
    ("scroll", ("down", 3)),
    ("type_text", ("hi", iter([]))),
    ("hotkey", ("cmd,s",)),
    ("press", ("enter",)),
    ("launch", ("App",)),
    ("focus_app", ("App",)),
]


@pytest.mark.parametrize("op,args", OPERATIONS)
def test_windows_backend_reports_unsupported_explicitly(op, args):
    b = WindowsBackend()
    with pytest.raises(CapabilityError) as e:
        getattr(b, op)(*args)
    assert e.value.capability == op


@pytest.mark.parametrize("op,args", OPERATIONS)
def test_linux_backend_reports_unsupported_explicitly(op, args):
    b = LinuxBackend()
    with pytest.raises(CapabilityError) as e:
        getattr(b, op)(*args)
    assert e.value.capability == op


def test_windows_linux_release_all_is_safe_noop():
    # release_all must never raise; nothing is ever held
    WindowsBackend().release_all()
    LinuxBackend().release_all()


def test_backend_names():
    assert WindowsBackend().backend_name() == "windows"
    assert LinuxBackend().backend_name() == "linux"


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS host only")
class TestMacosBackend:
    def _backend(self):
        from desktop.platforms.macos import MacosBackend

        return MacosBackend()

    def test_backend_name(self):
        assert self._backend().backend_name() == "macos"

    def test_trusted_readonly(self):
        try:
            result = self._backend().trusted()
        except CapabilityError as error:
            assert error.capability == "helper"
            return
        assert isinstance(result, bool)

    def test_cursor_readonly(self):
        try:
            pos = self._backend().cursor_position()
        except CapabilityError as error:
            assert error.capability == "helper"
            return
        assert len(pos) == 2 and all(isinstance(value, int) for value in pos)

    def test_screen_size_readonly(self):
        from desktop.platforms.base import CapabilityError

        b = self._backend()
        try:
            size = b.screen_size()
        except CapabilityError as e:
            # Screen Recording permission revoked mid-session: honest
            # capability failure is the correct behavior
            assert "0x0" in str(e) or "permission" in str(e).lower()
            return
        assert size["width"] > 0 and size["height"] > 0

    def test_active_window_readonly(self):
        from desktop.platforms.base import CapabilityError

        try:
            name = self._backend().active_window()
        except CapabilityError as error:
            assert error.capability == "active_window"
            return
        assert isinstance(name, str) and name
