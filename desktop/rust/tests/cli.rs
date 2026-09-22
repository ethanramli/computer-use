use serde_json::Value;
use std::process::{Command, Output};

fn run(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_desktop"))
        .args(args)
        .output()
        .expect("run desktop binary")
}

fn run_mock(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_desktop"))
        .args(args)
        .env("DESKTOP_FAKE_BACKEND", "1")
        .output()
        .expect("run desktop binary with mock provider")
}

fn envelope(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).expect("one JSON envelope on stdout")
}

#[test]
fn dry_run_is_default_and_stdout_is_json() {
    let output = run(&["click", "--x", "5", "--y", "6", "--risk", "none"]);
    assert_eq!(output.status.code(), Some(0));
    assert!(output.stderr.is_empty());
    assert_eq!(envelope(&output)["data"]["dry_run"], true);
}

#[test]
fn mock_provider_exposes_realistic_metadata_without_claiming_native_support() {
    let active = run_mock(&["active-window"]);
    assert_eq!(active.status.code(), Some(0));
    assert_eq!(envelope(&active)["data"]["active_window"], "Finder");

    let apps = run_mock(&["list_apps"]);
    assert_eq!(apps.status.code(), Some(4));
    assert_eq!(
        envelope(&apps)["error"]["message"],
        "not supported by this backend"
    );
    assert_eq!(
        envelope(&apps)["error"]["recover"],
        "'list_apps' is unavailable on fake"
    );
}

#[cfg(not(target_os = "macos"))]
#[test]
fn production_provider_reports_unsupported_on_unimplemented_hosts() {
    let unavailable = run(&["observe"]);
    assert_eq!(unavailable.status.code(), Some(4));
    assert_eq!(envelope(&unavailable)["error"]["code"], "unsupported");
}

#[test]
fn cli_errors_keep_public_execution_codes() {
    let bad_argument = run(&["click", "--x", "nope", "--y", "2"]);
    assert_eq!(bad_argument.status.code(), Some(2));
    assert_eq!(envelope(&bad_argument)["error"]["code"], "bad_arg");

    let blocked = run(&["hotkey", "cmd+shift+q"]);
    assert_eq!(blocked.status.code(), Some(4));
    assert_eq!(envelope(&blocked)["error"]["code"], "blocked");
}

#[test]
fn one_shot_coordinate_execution_requires_a_persistent_session() {
    let output = run(&[
        "click",
        "--x",
        "5",
        "--y",
        "6",
        "--frame-id",
        "frame-1",
        "--execute",
    ]);
    assert_eq!(output.status.code(), Some(4));
    let result = envelope(&output);
    assert_eq!(result["error"]["code"], "unsupported");
    assert!(
        result["error"]["recover"]
            .as_str()
            .unwrap()
            .contains("computer-mcp")
    );
}

#[test]
fn required_arguments_are_checked_before_cli_execution_restrictions() {
    let output = run(&["click", "--execute"]);
    assert_eq!(output.status.code(), Some(2));
    assert_eq!(envelope(&output)["error"]["code"], "bad_arg");
}

#[test]
fn click_type_maps_its_positional_text_and_required_fields() {
    let output = run(&[
        "click_type",
        "hello",
        "--app",
        "Finder",
        "--x",
        "10",
        "--y",
        "20",
        "--risk",
        "none",
    ]);
    assert_eq!(output.status.code(), Some(0));
    let result = envelope(&output);
    assert_eq!(result["data"]["typed"], 5);
    assert_eq!(result["data"]["app"], "Finder");
}

#[test]
fn help_lists_every_public_command() {
    let output = run(&["--help"]);
    assert_eq!(output.status.code(), Some(0));
    let help = String::from_utf8(output.stdout).unwrap();
    for command in [
        "observe",
        "list_apps",
        "list_windows",
        "active-window",
        "focus_app",
        "launch",
        "move",
        "click",
        "double-click",
        "right_click",
        "drag",
        "scroll",
        "type",
        "click_type",
        "press",
        "hotkey",
        "wait",
        "batch",
        "stop",
        "doctor",
    ] {
        assert!(help.contains(command), "missing {command}");
    }
    assert!(help.contains("click --x X --y Y"));
    assert!(help.contains("batch --json JSON"));
    assert!(help.contains("click_type TEXT --app APP --x X --y Y"));
}

#[cfg(target_os = "macos")]
#[test]
fn native_macos_doctor_reports_each_dependency_and_permission_separately() {
    let output = run(&["doctor", "--execute"]);
    assert_eq!(output.status.code(), Some(0));
    let result = envelope(&output);
    assert_eq!(result["data"]["platform"], "macos");
    let checks = result["data"]["checks"].as_object().unwrap();
    assert_eq!(
        checks
            .keys()
            .map(String::as_str)
            .collect::<std::collections::BTreeSet<_>>(),
        ["accessibility", "helper", "mss", "screen_recording"]
            .into_iter()
            .collect()
    );
    assert!(
        checks["mss"]["message"]
            .as_str()
            .unwrap()
            .contains("native Rust capture")
    );
}
