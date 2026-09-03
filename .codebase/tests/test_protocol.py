from desktop import input as inp, move, protocol, state


def test_ok_shape():
    assert protocol.ok({"a": 1}) == {"ok": True, "data": {"a": 1}}


def test_fail_shape():
    r = protocol.fail("bad_arg", "x invalid", "pass valid x")
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"


def test_single_frame():
    state.set_frame("/tmp/a.jpg")
    assert state.current_frame() == "/tmp/a.jpg"
    state.set_frame("/tmp/b.jpg")
    assert state.current_frame() == "/tmp/b.jpg"
    state.clear_frame()
    assert state.current_frame() is None


def test_move_exact_land_and_seed():
    a = move.points(0, 0, 640, 420, seed=7)
    b = move.points(0, 0, 640, 420, seed=7)
    assert a == b
    assert a[-1] == (640, 420)
    assert len(a) == 50


def test_safety_gates():
    assert inp.validate_xy(10, 20) is True
    assert inp.validate_xy(-1, 5) is False
    assert inp.is_blocked_keys("cmd+shift+q") is True
    assert inp.looks_like_challenge("verify you are human") is True
