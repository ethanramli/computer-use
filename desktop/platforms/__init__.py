"""Platform adapter selection. One backend per process, chosen by OS."""

import platform
from .base import Backend, CapabilityError, FocusError


def get_backend() -> Backend:
    system = platform.system()
    if system == "Darwin":
        from . import macos as _m
        return _m.MacosBackend()
    if system == "Windows":
        from . import windows as _w
        return _w.WindowsBackend()
    if system == "Linux":
        from . import linux as _l
        return _l.LinuxBackend()
    raise CapabilityError("platform", f"unsupported platform: {system}")
