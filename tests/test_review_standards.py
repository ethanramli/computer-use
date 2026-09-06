"""Regression tests for standards-review findings (2026-09-04)."""

import pytest

from desktop.platforms import macos
from desktop.safety import is_blocked_keys, key_parts, validate_keys


def test_keycodes_are_unique():
    # aliases (return/enter, esc/escape, delete/backspace) share codes
    # intentionally; distinct physical keys must not
    aliases = [("return", "enter"), ("esc", "escape"), ("delete", "backspace")]
    alias_codes = [macos.KEYCODES[a] for pair in aliases for a in pair]
    others = {k: v for k, v in macos.KEYCODES.items()
              if k not in {a for pair in aliases for a in pair}}
    assert len(list(others.values())) == len(set(others.values())), \
        "duplicate keycodes among distinct keys"
    assert alias_codes  # aliases still exist


def test_z_keycode_is_kvk_ansi_z():
    # kVK_ANSI_Z = 6; 26 is the '7' key
    assert macos.KEYCODES["z"] == 6
    assert macos.KEYCODES["7"] == 26


def test_hotkey_z_posts_keycode_6():
    seen = []
    macos.hotkey("z", post=seen.append)
    assert seen == [("hotkey", 6, 0)]


def test_key_separators_unified():
    # + - and , all normalize the same way
    assert key_parts("cmd+s") == ["cmd", "s"]
    assert key_parts("cmd-s") == ["cmd", "s"]
    assert key_parts("cmd,s") == ["cmd", "s"]
    assert validate_keys("cmd-s") == ["cmd", "s"]
    assert is_blocked_keys("cmd-shift-q") is True
    assert is_blocked_keys("cmd,shift,q") is True


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("q+shift+command", ["cmd", "shift", "q"]),
        ("delete-control-option", ["ctrl", "alt", "delete"]),
        ("alt,ctrl,delete", ["ctrl", "alt", "delete"]),
        ("l+win", ["win", "l"]),
    ],
)
def test_modifier_aliases_and_order_are_canonical(raw, canonical):
    assert key_parts(raw) == canonical
