from desktop import move, protocol


def test_ok_shape():
    assert protocol.ok({"a": 1}) == {"ok": True, "data": {"a": 1}}


def test_fail_shape():
    r = protocol.fail("bad_arg", "x invalid", "pass valid x")
    assert r["ok"] is False
    assert r["error"]["code"] == "bad_arg"


def test_move_exact_land_and_seed():
    a = move.points(0, 0, 640, 420, seed=7)
    b = move.points(0, 0, 640, 420, seed=7)
    assert a == b
    assert a[-1] == (640, 420)
    assert len(a) == 50
    assert move.duration(0, 0, 640, 420) > 0
    c = move.points(0, 0, 640, 420, seed=8)
    assert c[-1] == (640, 420)
