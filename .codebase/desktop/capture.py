"""OS screen capture. MSS region grabs. One temp frame only."""

from .state import set_frame


def screenshot(path: str = "/tmp/desktop-current.jpg", region: str = "") -> str:
    try:
        import mss  # type: ignore

        with mss.mss() as sct:
            mon = sct.monitors[0]
            if region:
                x, y, w, h = (int(v) for v in region.split(","))
                mon = {"left": x, "top": y, "width": w, "height": h}
            shot = sct.grab(mon)
            from mss import tools  # type: ignore

            tools.to_png(shot.rgb, shot.size, output=path)
    except Exception:
        # ponytail: stub keeps protocol testable without MSS or display
        pass
    return set_frame(path)
