"""CLI contract tests. Public seam: the installed `desktop` command.

Runs the real CLI in a subprocess with a fake backend via env var so tests
prove exit codes and JSON shapes through the actual public interface.
"""

import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_cli(args, execute=False, env_extra=None):
    env = dict(os.environ)
    env["DESKTOP_FAKE_BACKEND"] = "1"
    env["PYTHONPATH"] = REPO
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, "-m", "desktop.cli"] + args
    if execute:
        cmd = [sys.executable, "-m", "desktop.cli", "--execute"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    return r.returncode, json.loads(r.stdout) if r.stdout.strip() else None


def run_cli_raw(args):
    env = dict(os.environ)
    env["DESKTOP_FAKE_BACKEND"] = "1"
    env["PYTHONPATH"] = REPO
    return subprocess.run(
        [sys.executable, "-m", "desktop.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def test_cli_dry_run_click_exit_zero():
    code, out = run_cli(["click", "--x", "5", "--y", "6", "--risk", "none"])
    assert code == 0
    assert out["ok"] is True
    assert out["data"]["dry_run"] is True


def test_cli_dry_run_allows_negative_display_coordinates():
    code, out = run_cli([
        "click", "--x", "-5", "--y", "6", "--risk", "none",
    ])
    assert code == 0
    assert out["ok"] is True
    assert out["data"]["x"] == -5


def test_cli_needs_attention_exit_three():
    code, out = run_cli(["type", "enter your password"])
    assert code == 3
    assert out["error"]["code"] == "needs_attention"


def test_cli_blocked_exit_four():
    code, out = run_cli(["hotkey", "cmd+shift+q"])
    assert code == 4
    assert out["error"]["code"] == "blocked"


def test_cli_doctor():
    code, out = run_cli(["doctor"])
    assert code == 0
    assert out["data"]["platform"]
    assert set(out["data"]["checks"]) == {
        "helper", "accessibility", "screen_recording", "mss"
    }


def test_computer_mcp_help_terminates_with_truthful_stdio_usage():
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO
    result = subprocess.run(
        [sys.executable, "-m", "desktop.mcp_server", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=2,
    )

    assert result.returncode == 0
    assert "stdio" in result.stdout.lower()


def test_cli_stop_honest_no_controller():
    code, out = run_cli(["stop"])
    assert code == 0
    assert out["ok"] is True
    assert out["data"]["stopped"] is False
    import inspect
    import desktop.cli as cli
    import desktop.controller as controller
    assert "desktop-stop-flag" not in inspect.getsource(cli)
    assert "desktop-stop-flag" not in inspect.getsource(controller)
    # the next unrelated command must run normally
    code2, out2 = run_cli(["wait", "--seconds", "0.01"])
    assert code2 == 0
    assert out2["ok"] is True


def test_cli_stop_environment_cannot_enable_removed_file_channel():
    code, out = run_cli(["stop"], env_extra={"DESKTOP_MCP_STOP": "1"})
    assert code == 0
    assert out["data"]["stopped"] is False


def test_cli_launch_dry_run():
    code, out = run_cli(["launch", "--app", "Chrome"])
    assert code == 0
    assert out["data"]["dry_run"] is True


def test_cli_observe_dry_run():
    code, out = run_cli(["observe"])
    assert code == 0
    assert out["ok"] is True


def test_cli_help_lists_all_commands():
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO
    r = subprocess.run([sys.executable, "-m", "desktop.cli", "--help"],
                       capture_output=True, text=True, env=env, timeout=30)
    for name in ("observe", "list_apps", "list_windows", "active-window",
                 "focus_app", "launch", "move", "click", "double-click",
                 "right_click", "drag", "scroll", "type", "click_type",
                 "press", "hotkey", "wait", "batch", "stop", "doctor"):
        assert name in r.stdout, f"missing {name} in help"


def test_cli_parse_failure_is_exactly_one_json_envelope_on_stdout():
    result = run_cli_raw(["click", "--x", "not-an-int", "--y", "2"])

    assert result.returncode == 2
    assert result.stderr == ""
    lines = result.stdout.splitlines()
    assert len(lines) == 1
    envelope = json.loads(lines[0])
    assert envelope["error"]["code"] == "bad_arg"


def test_execute_is_supported_after_the_subcommand_as_documented():
    result = run_cli_raw(["wait", "--seconds", "0", "--execute"])

    assert result.returncode == 0
    assert json.loads(result.stdout)["data"]["executed"] is True


def test_global_flag_name_can_be_escaped_as_literal_text():
    result = run_cli_raw(
        ["type", "--app", "Finder", "--risk", "none", "--", "--execute"]
    )

    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["data"]["typed"] == len("--execute")
    assert envelope["data"]["dry_run"] is True


def test_one_shot_cli_refuses_execute_coordinate_action_without_session():
    result = run_cli_raw(
        ["click", "--x", "1", "--y", "2", "--frame-id", "frame-1", "--execute"]
    )

    assert result.returncode == 4
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "unsupported"
    assert "computer-mcp" in envelope["error"]["recover"]


def test_one_shot_cli_refuses_path_mode_that_cannot_outlive_process():
    result = run_cli_raw(["observe", "--to-file", "--execute"])

    assert result.returncode == 4
    assert json.loads(result.stdout)["error"]["code"] == "unsupported"


def test_batch_json_must_be_an_object():
    result = run_cli_raw(["batch", "--json", "[]"])

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "bad_arg"
