use serde_json::{Value, json};

pub const COMMANDS: &[&str] = &[
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
];

pub fn ok(data: Value) -> Value {
    json!({"ok": true, "data": data})
}

pub fn fail(code: &str, message: &str, recover: &str) -> Value {
    let mut error = json!({"code": code, "message": message});
    if !recover.is_empty() {
        error["recover"] = json!(recover);
    }
    json!({"ok": false, "error": error})
}

pub fn partial(data: Value, code: &str, message: &str, recover: &str) -> Value {
    let mut envelope = fail(code, message, recover);
    envelope["data"] = data;
    envelope
}
