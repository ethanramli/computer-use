"""Safety validation. Blocklists, challenge detection, confirmation gates."""

import pytest

from desktop.safety import (
    input_state_issue,
    is_blocked_keys,
    looks_like_challenge,
    needs_confirmation,
    validate_batch,
    validate_coordinates,
    validate_keys,
    validate_region,
    validate_text,
)


def test_coordinates_allow_negative_display_origins_but_reject_non_int():
    assert validate_coordinates(10, 20) is True
    assert validate_coordinates(-1, 5) is True
    assert validate_coordinates(1.5, 5) is False


def test_region_validates_signed_origin_and_positive_size():
    assert validate_region("0,0,800,600") == (0, 0, 800, 600)
    assert validate_region("-800,-20,800,600") == (-800, -20, 800, 600)
    assert validate_region("") is None
    with pytest.raises(ValueError):
        validate_region("0,0,-5,600")
    with pytest.raises(ValueError):
        validate_region("0,0,800")
    with pytest.raises(ValueError):
        validate_region("0,0,0,0")


def test_blocked_keys_exact_match():
    assert is_blocked_keys("cmd+shift+q") is True
    assert is_blocked_keys("alt-f4") is True
    assert is_blocked_keys("cmd+s") is False


def test_unknown_keys_rejected():
    assert validate_keys("cmd,s") == ["cmd", "s"]
    with pytest.raises(ValueError):
        validate_keys("cmd,notakey!!")


def test_challenge_detection():
    assert looks_like_challenge("verify you are human") is True
    assert looks_like_challenge("enter your password") is True
    assert looks_like_challenge("hello world") is False


def test_empty_accessibility_metadata_fails_closed():
    issue = input_state_issue({"role": "", "title": ""})

    assert issue is not None
    assert issue.code == "needs_attention"


@pytest.mark.parametrize("subrole", ["AXDialog", "AXSystemDialog"])
def test_dialog_window_metadata_fails_closed(subrole):
    issue = input_state_issue(
        {"role": "AXTextField", "window_subrole": subrole}
    )

    assert issue is not None
    assert issue.code == "needs_attention"


def test_consequential_actions_require_confirmation():
    # classification of known risky intents by label
    assert needs_confirmation("delete the file") is True
    assert needs_confirmation("purchase") is True
    assert needs_confirmation("hello") is False


def test_text_validation_bounds():
    assert validate_text("hello") == "hello"
    with pytest.raises(ValueError):
        validate_text("")
    with pytest.raises(ValueError):
        validate_text("x" * 100_001)


def test_batch_validation_rejects_before_first_action():
    ok, err = validate_batch([
        {"op": "click", "x": 10, "y": 20, "risk": "none"},
        {"op": "type", "text": "hi", "app": "Finder", "risk": "none"},
    ])
    assert ok is True and err is None
    ok, err = validate_batch([{"op": "nonsense"}])
    assert ok is False and "unknown op" in err
    ok, err = validate_batch([{"op": "click", "x": -1, "y": 0, "risk": "none"}])
    assert ok is True and err is None
    ok, err = validate_batch([])
    assert ok is False and "empty" in err
    ok, err = validate_batch(
        [{"op": "click", "x": 1, "y": 2, "risk": "none"}] * 501
    )
    assert ok is False and "too many" in err
