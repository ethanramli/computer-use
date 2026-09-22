use computer_automation::frames::{Display, DisplayLayout, FrameStore};
use computer_automation::motion::{movement_time, points};
use computer_automation::protocol::{fail, ok, partial};
use computer_automation::timing::gaps_for_seed;
use computer_automation::{BackendResult, Controller, DesktopBackend, MockBackend};
use serde_json::json;
use std::sync::{Arc, Mutex};

const ONE_PIXEL_PNG: &[u8] = &[
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x04, 0x00, 0x00, 0x00, 0xb5, 0x1c, 0x0c,
    0x02, 0x00, 0x00, 0x00, 0x0b, 0x49, 0x44, 0x41, 0x54, 0x78, 0xda, 0x63, 0x64, 0xf8, 0x0f, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x27, 0x18, 0xe3, 0x66, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44,
    0xae, 0x42, 0x60, 0x82,
];

struct CapturingBackend;

impl DesktopBackend for CapturingBackend {
    fn display_layout(&self) -> BackendResult<serde_json::Value> {
        Ok(json!({
            "origin": [0, 0],
            "width": 1440,
            "height": 900,
            "displays": [{
                "id": "capture-display",
                "origin": [0, 0],
                "width": 1440,
                "height": 900,
                "scale": [1.0, 1.0],
                "rotation": 0.0
            }]
        }))
    }

    fn active_window(&self) -> BackendResult<String> {
        Ok("Editor".into())
    }

    fn capture_png(&self, _x: i64, _y: i64, _width: i64, _height: i64) -> BackendResult<Vec<u8>> {
        Ok(ONE_PIXEL_PNG.to_vec())
    }

    fn backend_name(&self) -> &'static str {
        "capture-fixture"
    }
}

struct RecordingBackend {
    events: Arc<Mutex<Vec<&'static str>>>,
}

struct ChangingFocusBackend {
    events: Arc<Mutex<Vec<&'static str>>>,
}

struct EffectBackend {
    value: Arc<Mutex<String>>,
}

impl DesktopBackend for EffectBackend {
    fn display_layout(&self) -> BackendResult<serde_json::Value> {
        CapturingBackend.display_layout()
    }

    fn active_window(&self) -> BackendResult<String> {
        Ok("Editor".into())
    }

    fn focused_element(&self) -> BackendResult<serde_json::Value> {
        Ok(json!({"role": "AXTextArea", "value": *self.value.lock().unwrap()}))
    }

    fn cursor_position(&self) -> BackendResult<(i64, i64)> {
        Ok((0, 0))
    }

    fn move_path(
        &self,
        _points: &[(i64, i64)],
        _total_secs: f64,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        Ok(())
    }

    fn type_text(
        &self,
        text: &str,
        _gaps: &[f64],
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<usize> {
        self.value.lock().unwrap().push_str(text);
        Ok(text.chars().count())
    }

    fn key(&self, _keys: &str, _cancelled: &dyn Fn() -> bool) -> BackendResult<()> {
        Ok(())
    }
}

impl DesktopBackend for ChangingFocusBackend {
    fn display_layout(&self) -> BackendResult<serde_json::Value> {
        CapturingBackend.display_layout()
    }

    fn active_window(&self) -> BackendResult<String> {
        if self.events.lock().unwrap().is_empty() {
            Ok("Editor".into())
        } else {
            Ok("Other".into())
        }
    }

    fn focused_element(&self) -> BackendResult<serde_json::Value> {
        Ok(json!({"role": "AXTextArea", "secure": false}))
    }

    fn cursor_position(&self) -> BackendResult<(i64, i64)> {
        Ok((0, 0))
    }

    fn move_path(
        &self,
        _points: &[(i64, i64)],
        _total_secs: f64,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        self.events.lock().unwrap().push("move");
        Ok(())
    }

    fn scroll(
        &self,
        _direction: &str,
        _amount: usize,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        self.events.lock().unwrap().push("scroll");
        Ok(())
    }

    fn backend_name(&self) -> &'static str {
        "changing-focus"
    }
}

impl DesktopBackend for RecordingBackend {
    fn display_layout(&self) -> BackendResult<serde_json::Value> {
        CapturingBackend.display_layout()
    }

    fn active_window(&self) -> BackendResult<String> {
        Ok("Editor".into())
    }

    fn capture_png(&self, x: i64, y: i64, width: i64, height: i64) -> BackendResult<Vec<u8>> {
        CapturingBackend.capture_png(x, y, width, height)
    }

    fn cursor_position(&self) -> BackendResult<(i64, i64)> {
        Ok((0, 0))
    }

    fn focused_element(&self) -> BackendResult<serde_json::Value> {
        Ok(json!({"role": "AXTextArea", "secure": false}))
    }

    fn element_at(&self, _x: i64, _y: i64) -> BackendResult<serde_json::Value> {
        self.focused_element()
    }

    fn move_path(
        &self,
        _points: &[(i64, i64)],
        _total_secs: f64,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        self.events.lock().unwrap().push("move");
        Ok(())
    }

    fn click(
        &self,
        _x: i64,
        _y: i64,
        _button: &str,
        _double: bool,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        self.events.lock().unwrap().push("click");
        Ok(())
    }

    fn drag(
        &self,
        _from: (i64, i64),
        _to: (i64, i64),
        _path: &[(i64, i64)],
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        self.events.lock().unwrap().push("drag");
        Ok(())
    }

    fn scroll(
        &self,
        _direction: &str,
        _amount: usize,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        self.events.lock().unwrap().push("scroll");
        Ok(())
    }

    fn type_text(
        &self,
        text: &str,
        _gaps: &[f64],
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<usize> {
        self.events.lock().unwrap().push("type");
        Ok(text.chars().count())
    }

    fn key(&self, _keys: &str, _cancelled: &dyn Fn() -> bool) -> BackendResult<()> {
        self.events.lock().unwrap().push("key");
        Ok(())
    }

    fn backend_name(&self) -> &'static str {
        "recording"
    }
}

#[test]
fn public_result_envelopes_match_the_python_contract() {
    assert_eq!(
        ok(json!({"active_window": "Mock App"})),
        json!({
            "ok": true,
            "data": {"active_window": "Mock App"}
        })
    );

    assert_eq!(
        fail("bad_arg", "invalid x", "fix the argument"),
        json!({
            "ok": false,
            "error": {
                "code": "bad_arg",
                "message": "invalid x",
                "recover": "fix the argument"
            }
        })
    );

    assert_eq!(
        fail("unsupported", "not available", ""),
        json!({
            "ok": false,
            "error": {"code": "unsupported", "message": "not available"}
        })
    );

    assert_eq!(
        partial(json!({"last_completed": 0}), "cancelled", "stopped", ""),
        json!({
            "ok": false,
            "error": {"code": "cancelled", "message": "stopped"},
            "data": {"last_completed": 0}
        })
    );
}

#[test]
fn dry_run_observe_matches_the_current_command_contract() {
    let mut controller = Controller::new(MockBackend, true);
    assert_eq!(
        controller.command("observe", &json!({})),
        json!({
            "ok": true,
            "data": {
                "region": [0, 0, 1440, 900],
                "layout": {
                    "origin": [0, 0],
                    "width": 1440,
                    "height": 900,
                    "displays": [{
                        "id": "fake-display",
                        "origin": [0, 0],
                        "width": 1440,
                        "height": 900,
                        "scale": [1.0, 1.0],
                        "rotation": 0.0
                    }]
                },
                "dry_run": true
            }
        })
    );
}

#[test]
fn dry_run_observe_rejects_a_region_outside_the_reported_layout() {
    let mut controller = Controller::new(MockBackend, true);
    assert_eq!(
        controller.command("observe", &json!({"region": "1900,0,40,20"})),
        json!({
            "ok": false,
            "error": {
                "code": "bad_arg",
                "message": "capture region is outside the current display layout",
                "recover": "choose a region inside the reported layout bounds"
            }
        })
    );
}

#[test]
fn live_observe_returns_owned_png_and_metadata_only_replaces_the_frame() {
    let mut controller = Controller::new(CapturingBackend, false);
    let image = controller.command("observe", &json!({}));
    assert_eq!(image["ok"], true);
    assert_eq!(
        image["data"]["image_b64"],
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    );
    assert_eq!(image["data"]["active_window"], "Editor");

    let metadata = controller.command("observe", &json!({"metadata_only": true}));
    assert_eq!(metadata["ok"], true);
    assert!(metadata["data"].get("image_b64").is_none());
    assert_ne!(metadata["data"]["frame_id"], image["data"]["frame_id"]);
}

#[test]
fn live_path_observe_uses_one_private_file_and_removes_it_on_drop() {
    let path;
    {
        let mut controller = Controller::new(CapturingBackend, false);
        let first = controller.command("observe", &json!({"path_mode": true}));
        assert_eq!(first["ok"], true, "{first}");
        path = std::path::PathBuf::from(first["data"]["path"].as_str().unwrap());
        assert!(path.is_file());
        let second = controller.command("observe", &json!({"path_mode": true}));
        assert_eq!(second["data"]["path"].as_str(), path.to_str());
    }
    assert!(!path.exists());
}

#[test]
fn live_keyboard_input_fails_closed_when_accessibility_state_is_unknown() {
    let mut controller = Controller::new(CapturingBackend, false);
    let result = controller.command(
        "type",
        &json!({"text": "hello", "app": "Editor", "risk": "none"}),
    );
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"]["code"], "needs_attention");
    assert_eq!(
        result["error"]["message"],
        "input safety state could not be inspected"
    );
}

#[test]
fn live_click_visibly_moves_before_dispatching_input() {
    let events = Arc::new(Mutex::new(Vec::new()));
    let mut controller = Controller::new(
        RecordingBackend {
            events: Arc::clone(&events),
        },
        false,
    );
    let observed = controller.command("observe", &json!({"metadata_only": true}));
    let result = controller.command(
        "click",
        &json!({
            "x": 20,
            "y": 30,
            "frame_id": observed["data"]["frame_id"],
            "risk": "none"
        }),
    );
    assert_eq!(result["ok"], true);
    assert_eq!(*events.lock().unwrap(), ["move", "click"]);
}

#[test]
fn remaining_live_input_commands_are_dispatched_after_visible_travel() {
    let cases = [
        (
            "drag",
            json!({
                "from_x": 5, "from_y": 6, "to_x": 20, "to_y": 30,
                "risk": "none"
            }),
            &["move", "drag"][..],
        ),
        (
            "double-click",
            json!({"x": 20, "y": 30, "risk": "none"}),
            &["move", "click"],
        ),
        (
            "right_click",
            json!({"x": 20, "y": 30, "risk": "none"}),
            &["move", "click"],
        ),
        (
            "scroll",
            json!({"direction": "down", "amount": 2, "risk": "none"}),
            &["move", "scroll"],
        ),
        (
            "type",
            json!({"text": "hi", "app": "Editor", "risk": "none"}),
            &["move", "type"],
        ),
        (
            "click_type",
            json!({"x": 5, "y": 6, "text": "hi", "app": "Editor", "risk": "none"}),
            &["move", "click", "type"],
        ),
        (
            "press",
            json!({"keys": "enter", "app": "Editor", "risk": "none"}),
            &["move", "key"],
        ),
        (
            "hotkey",
            json!({"keys": "cmd+a", "app": "Editor", "risk": "none"}),
            &["move", "key"],
        ),
    ];

    for (command, mut params, expected) in cases {
        let events = Arc::new(Mutex::new(Vec::new()));
        let mut controller = Controller::new(
            RecordingBackend {
                events: Arc::clone(&events),
            },
            false,
        );
        if matches!(
            command,
            "click" | "double-click" | "right_click" | "drag" | "click_type"
        ) {
            let observed = controller.command("observe", &json!({"metadata_only": true}));
            params["frame_id"] = observed["data"]["frame_id"].clone();
        }
        let result = controller.command(command, &params);
        assert_eq!(result["ok"], true, "{command}: {result}");
        assert_eq!(&*events.lock().unwrap(), expected, "{command}");
    }
}

#[test]
fn live_batch_rechecks_focus_after_each_state_changing_action() {
    let events = Arc::new(Mutex::new(Vec::new()));
    let mut controller = Controller::new(
        ChangingFocusBackend {
            events: Arc::clone(&events),
        },
        false,
    );
    let result = controller.command(
        "batch",
        &json!({
            "app": "Editor",
            "risk": "none",
            "actions": [
                {"op": "scroll", "direction": "down", "amount": 1},
                {"op": "type", "text": "should not be typed"}
            ]
        }),
    );
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"]["code"], "focus_failed");
    assert_eq!(result["data"]["last_completed"], 0);
    assert_eq!(*events.lock().unwrap(), ["move", "scroll"]);
}

#[test]
fn nested_live_batch_inherits_outer_app_and_risk_context() {
    let events = Arc::new(Mutex::new(Vec::new()));
    let mut controller = Controller::new(
        RecordingBackend {
            events: Arc::clone(&events),
        },
        false,
    );
    let result = controller.command(
        "batch",
        &json!({
            "app": "Editor",
            "risk": "none",
            "actions": [{
                "op": "batch",
                "actions": [{"op": "type", "text": "nested"}]
            }]
        }),
    );
    assert_eq!(result["ok"], true, "{result}");
    assert_eq!(*events.lock().unwrap(), ["move", "type"]);
}

#[test]
fn live_batch_deadline_interrupts_a_running_wait() {
    let mut controller = Controller::new(MockBackend, false);
    let started = std::time::Instant::now();
    let result = controller.command(
        "batch",
        &json!({
            "deadline_ms": 20,
            "actions": [{"op": "wait", "seconds": 1}]
        }),
    );
    assert!(started.elapsed() < std::time::Duration::from_millis(250));
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"]["code"], "deadline_exceeded");
    assert_eq!(result["data"]["status"], "deadline_exceeded");
    assert_eq!(result["data"]["last_completed"], -1);
}

#[test]
fn live_typing_reports_only_proven_effects() {
    let value = Arc::new(Mutex::new("before".to_owned()));
    let mut controller = Controller::new(
        EffectBackend {
            value: Arc::clone(&value),
        },
        false,
    );
    let result = controller.command(
        "type",
        &json!({
            "text": "hi",
            "app": "Editor",
            "verify": "effect",
            "risk": "none"
        }),
    );
    assert_eq!(result["ok"], true);
    assert_eq!(result["data"]["effect_verified"], true);

    let focused = controller.command(
        "press",
        &json!({
            "keys": "enter",
            "app": "Editor",
            "verify": "focus",
            "risk": "none"
        }),
    );
    assert_eq!(focused["data"]["effect_verified"], true);
}

#[test]
fn confirmation_gate_runs_before_backend_dispatch() {
    let mut controller = Controller::new(MockBackend, true);
    assert_eq!(
        controller.command("click", &json!({"x": 3, "y": 4, "risk": "deletion"})),
        json!({
            "ok": false,
            "error": {
                "code": "needs_attention",
                "message": "consequential input requires fresh confirmation with confirm: true",
                "recover": "fix the command and retry"
            }
        })
    );
}

#[test]
fn command_specific_arguments_are_checked_before_dispatch() {
    let mut controller = Controller::new(MockBackend, true);
    let result = controller.command(
        "click",
        &json!({"x": 3, "y": 4, "risk": "none", "target": "Finder"}),
    );
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"]["code"], "bad_arg");
    assert_eq!(
        result["error"]["message"],
        "unknown argument(s): target. did you mean 'app'? keyboard input needs 'app'"
    );
}

#[test]
fn seeded_motion_matches_the_python_path_fixture() {
    assert_eq!(
        points((0, 0), (100, 100), 7, 5),
        vec![(59, 63), (97, 101), (103, 106), (102, 103), (100, 100)]
    );
    assert_eq!(
        points((320, 240), (640, 420), 19, 10),
        vec![
            (366, 274),
            (449, 319),
            (520, 352),
            (573, 378),
            (604, 400),
            (621, 405),
            (632, 413),
            (636, 416),
            (639, 419),
            (640, 420),
        ]
    );
    assert!((movement_time(100.0_f64.hypot(100.0), 80.0) - 0.7824780249076275).abs() < 1e-12);
}

#[test]
fn seeded_typing_gaps_match_the_python_fixture() {
    let actual = gaps_for_seed("human", "hello", 0).unwrap();
    let expected = [
        0.17579544029403027,
        0.12589167502929635,
        0.14049341374504143,
        0.13033127260789276,
        0.15833820394550313,
    ];
    assert!(
        actual
            .iter()
            .zip(expected)
            .all(|(a, b)| (a - b).abs() < 1e-15)
    );
    assert_eq!(gaps_for_seed("native", "hello", 0).unwrap(), vec![0.0; 5]);
    assert_eq!(
        gaps_for_seed("compatibility", "hi", 0).unwrap(),
        vec![0.01; 2]
    );
}

#[test]
fn frame_store_keeps_only_the_current_image_and_authorizes_signed_origins() {
    let layout = DisplayLayout {
        origin: [-1280, 0],
        width: 3200,
        height: 1080,
        displays: vec![
            Display {
                id: "left".into(),
                origin: [-1280, 0],
                width: 1280,
                height: 1024,
                scale: [1.0, 1.0],
                rotation: 0.0,
            },
            Display {
                id: "main".into(),
                origin: [0, 0],
                width: 1920,
                height: 1080,
                scale: [2.0, 2.0],
                rotation: 0.0,
            },
        ],
    };
    assert!(layout.validate().is_ok());
    assert!(layout.contains_point(-100, 20));
    assert!(!layout.contains_point(3200, 20));

    let mut frames = FrameStore::new(1024).unwrap();
    let old = frames
        .insert(
            layout.clone(),
            (-100, 20, 200, 100),
            "Editor",
            Some(vec![1, 2, 3]),
        )
        .unwrap()
        .id
        .clone();
    assert!(frames.authorizes(&old, &layout, "Editor", &[(-50, 30)]));
    assert!(!frames.authorizes(&old, &layout, "Editor", &[(101, 30)]));
    let new = frames
        .insert(layout.clone(), (0, 0, 20, 20), "Editor", None)
        .unwrap()
        .id
        .clone();
    assert_eq!(frames.len(), 1);
    assert!(frames.get(&old).is_none());
    assert!(frames.get(&new).is_some());
}

#[test]
fn invalid_or_oversized_frames_are_rejected_without_replacing_current_frame() {
    let layout = DisplayLayout {
        origin: [0, 0],
        width: 100,
        height: 100,
        displays: vec![Display {
            id: "main".into(),
            origin: [0, 0],
            width: 100,
            height: 100,
            scale: [1.0, 1.0],
            rotation: 0.0,
        }],
    };
    let mut frames = FrameStore::new(260).unwrap();
    let current = frames
        .insert(layout.clone(), (0, 0, 10, 10), "Editor", Some(vec![1]))
        .unwrap()
        .id
        .clone();
    assert!(
        frames
            .insert(layout.clone(), (0, 0, 10, 10), "Editor", Some(vec![0; 5]))
            .is_err()
    );
    assert_eq!(frames.latest().unwrap().id, current);
    let mut invalid = layout;
    invalid.displays[0].scale = [0.0, 1.0];
    assert!(invalid.validate().is_err());
}

#[test]
fn dry_run_input_commands_return_compatible_plans_after_safety_preflight() {
    let mut controller = Controller::new(MockBackend, true);
    assert_eq!(
        controller.command("click", &json!({"x": 3, "y": 4, "risk": "none"})),
        json!({"ok": true, "data": {"x": 3, "y": 4, "op": "click", "dry_run": true}})
    );
    assert_eq!(
        controller.command(
            "type",
            &json!({"text": "hello", "app": "Finder", "risk": "none"})
        ),
        json!({"ok": true, "data": {"typed": 5, "dry_run": true}})
    );
    assert_eq!(
        controller.command(
            "move",
            &json!({"x": 10, "y": 20, "risk": "none", "seed": 7})
        ),
        json!({"ok": true, "data": {"x": 10, "y": 20, "points": 50, "dry_run": true}})
    );
}

#[test]
fn batch_dry_run_returns_ordered_receipts_after_whole_batch_preflight() {
    let mut controller = Controller::new(MockBackend, true);
    let result = controller.command(
        "batch",
        &json!({
        "actions": [
            {"op": "click", "x": 3, "y": 4},
            {"op": "scroll", "direction": "down", "amount": 1}
            ],
            "risk": "none"
        }),
    );
    assert_eq!(result["ok"], true);
    assert_eq!(result["data"]["status"], "completed");
    assert_eq!(result["data"]["last_completed"], 1);
    assert_eq!(result["data"]["receipts"][0]["index"], 0);
    assert_eq!(result["data"]["receipts"][1]["index"], 1);
}

#[test]
fn batch_rejects_a_late_invalid_action_before_any_receipt() {
    let mut controller = Controller::new(MockBackend, true);
    let result = controller.command(
        "batch",
        &json!({
        "actions": [
            {"op": "click", "x": 3, "y": 4},
            {"op": "click", "x": 3}
            ],
            "risk": "none"
        }),
    );
    assert_eq!(result["ok"], false);
    assert_eq!(result["error"]["code"], "bad_arg");
    assert_eq!(result["error"]["message"], "action 1: y must be an integer");
    assert!(result.get("data").is_none());
}

#[test]
fn batch_risk_is_inherited_only_by_input_actions() {
    let mut controller = Controller::new(MockBackend, true);
    let result = controller.command(
        "batch",
        &json!({
            "risk": "none",
            "confirm": true,
            "actions": [
                {"op": "wait", "seconds": 0},
                {"op": "scroll", "direction": "down", "amount": 1}
            ]
        }),
    );
    assert_eq!(result["ok"], true);
    assert_eq!(result["data"]["last_completed"], 1);
}

#[test]
fn batch_final_observe_options_follow_python_validation_contract() {
    let mut controller = Controller::new(MockBackend, true);
    let actions = json!({
        "actions": [{"op": "scroll", "direction": "down", "amount": 1}],
        "risk": "none"
    });
    let valid = controller.command(
        "batch",
        &json!({"actions": actions["actions"], "risk": "none", "final_observe": {"image": true}}),
    );
    assert_eq!(valid["ok"], true);
    assert_eq!(valid["data"]["final_observation"]["ok"], true);
    assert_eq!(valid["data"]["final_observation"]["data"]["dry_run"], true);
    assert!(valid["data"].get("image_b64").is_none());

    let metadata = controller.command(
        "batch",
        &json!({
            "actions": actions["actions"],
            "risk": "none",
            "final_observe": {"image": false}
        }),
    );
    assert_eq!(metadata["data"]["final_observation"]["ok"], true);
    assert_eq!(
        metadata["data"]["final_observation"]["data"]["layout"]["width"],
        1440
    );

    for invalid in [json!(true), json!({"image": 1}), json!({"path_mode": true})] {
        let result = controller.command(
            "batch",
            &json!({"actions": actions["actions"], "risk": "none", "final_observe": invalid}),
        );
        assert_eq!(result["ok"], false);
        assert_eq!(result["error"]["code"], "bad_arg");
    }
}

#[test]
fn live_rust_batch_returns_one_final_image_after_action_receipts() {
    let mut controller = Controller::new(MockBackend, false);
    let result = controller.command(
        "batch",
        &json!({
            "actions": [{"op": "wait", "seconds": 0}],
            "final_observe": {"image": true}
        }),
    );
    assert_eq!(result["ok"], true);
    assert_eq!(result["data"]["final_observation"]["ok"], true);
    assert!(result["data"]["image_b64"].as_str().is_some());
    assert!(
        result["data"]["final_observation"]["data"]
            .get("image_b64")
            .is_none()
    );
}

#[test]
fn cancellation_handle_interrupts_an_active_wait() {
    let mut controller = Controller::new(MockBackend, false);
    let cancellation = controller.cancellation_handle();
    std::thread::scope(|scope| {
        let worker = scope.spawn(move || {
            controller.command_with_request_id("wait", &json!({"seconds": 10.0}), Some(json!(41)))
        });
        std::thread::sleep(std::time::Duration::from_millis(20));
        assert!(!cancellation.cancel_request(&json!(42), None));
        assert!(!cancellation.cancel_request(&json!(41), Some(2)));
        assert!(cancellation.cancel_request(&json!(41), Some(1)));
        let result = worker.join().expect("wait worker");
        assert_eq!(result["ok"], false);
        assert_eq!(result["error"]["code"], "cancelled");
    });
}

#[test]
fn cancellation_stops_batch_before_dispatching_the_next_action() {
    let mut controller = Controller::new(MockBackend, false);
    let cancellation = controller.cancellation_handle();
    std::thread::scope(|scope| {
        let worker = scope.spawn(move || {
            controller.command(
                "batch",
                &json!({
                    "actions": [
                        {"op": "wait", "seconds": 10.0},
                        {"op": "scroll", "direction": "down", "amount": 1, "risk": "none"}
                    ]
                }),
            )
        });
        std::thread::sleep(std::time::Duration::from_millis(20));
        let did_cancel = cancellation.cancel();
        let result = worker.join().expect("batch worker");
        assert!(did_cancel);
        assert_eq!(result["ok"], false);
        assert_eq!(result["error"]["code"], "cancelled");
        assert_eq!(result["data"]["status"], "cancelled");
        assert_eq!(result["data"]["last_completed"], -1);
        assert_eq!(result["data"]["receipts"].as_array().unwrap().len(), 1);
    });
}
