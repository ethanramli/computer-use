use serde_json::{Map, Value};
use std::collections::BTreeSet;

const MAX_TEXT: usize = 100_000;
const MAX_BATCH_ACTIONS: usize = 500;
const MAX_COMMAND_BYTES: usize = 4 * 1024 * 1024;

const INPUT_COMMANDS: &[&str] = &[
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
];
const KEYBOARD_COMMANDS: &[&str] = &["type", "click_type", "press", "hotkey"];
const COORDINATE_COMMANDS: &[&str] = &[
    "move",
    "click",
    "double-click",
    "right_click",
    "drag",
    "click_type",
];

pub fn is_input_command(command: &str) -> bool {
    INPUT_COMMANDS.contains(&command)
}

pub fn is_keyboard_command(command: &str) -> bool {
    KEYBOARD_COMMANDS.contains(&command)
}

pub fn is_coordinate_command(command: &str) -> bool {
    COORDINATE_COMMANDS.contains(&command)
}

#[derive(Debug, PartialEq, Eq)]
pub struct ValidationError {
    pub code: &'static str,
    pub message: String,
}

fn issue(code: &'static str, message: impl Into<String>) -> ValidationError {
    ValidationError {
        code,
        message: message.into(),
    }
}

pub fn preflight(command: &str, params: &Value) -> Result<(), ValidationError> {
    let object = params
        .as_object()
        .ok_or_else(|| issue("bad_arg", "params must be an object"))?;
    if serde_json::to_vec(params).map_or(true, |bytes| bytes.len() > MAX_COMMAND_BYTES) {
        return Err(issue(
            "bad_arg",
            format!("command payload exceeds {MAX_COMMAND_BYTES} UTF-8 bytes"),
        ));
    }
    if !crate::protocol::COMMANDS.contains(&command) {
        return Err(issue("bad_arg", format!("unknown command: {command}")));
    }
    validate_fields(command, object)?;
    validate_common(object)?;

    match command {
        "observe" => {
            if let Some(region) = object.get("region") {
                match region.as_str() {
                    Some(text) => {
                        parse_region(text)?;
                    }
                    None => return Err(issue("bad_arg", "region must be a string")),
                }
            }
            for flag in ["metadata_only", "path_mode"] {
                if object.get(flag).is_some_and(|value| !value.is_boolean()) {
                    return Err(issue("bad_arg", format!("{flag} must be a boolean")));
                }
            }
            if object.get("metadata_only") == Some(&Value::Bool(true))
                && object.get("path_mode") == Some(&Value::Bool(true))
            {
                return Err(issue(
                    "bad_arg",
                    "metadata_only and path_mode cannot both be true",
                ));
            }
        }
        "focus_app" | "launch" => require_app(object)?,
        "move" | "click" | "double-click" | "right_click" => {
            require_integer(object, "x")?;
            require_integer(object, "y")?;
        }
        "drag" => {
            for key in ["from_x", "from_y", "to_x", "to_y"] {
                require_integer(object, key)?;
            }
        }
        "scroll" => {
            let direction = object
                .get("direction")
                .and_then(Value::as_str)
                .unwrap_or("down");
            if !["up", "down", "left", "right"].contains(&direction) {
                return Err(issue("bad_arg", "direction must be up/down/left/right"));
            }
            let amount = object.get("amount").and_then(Value::as_i64).unwrap_or(3);
            if object
                .get("amount")
                .is_some_and(|v| v.as_i64().is_none() || v.as_bool().is_some())
                || !(1..=100).contains(&amount)
            {
                return Err(issue("bad_arg", "amount must be an integer from 1-100"));
            }
        }
        "type" | "click_type" => {
            if command == "click_type" {
                require_integer(object, "x")?;
                require_integer(object, "y")?;
            }
            let text = object
                .get("text")
                .and_then(Value::as_str)
                .ok_or_else(|| issue("bad_arg", "text must be a non-empty string"))?;
            validate_text(text)?;
            if looks_like_challenge(text) {
                return Err(issue(
                    "needs_attention",
                    "text mentions password/permission/payment/challenge UI",
                ));
            }
        }
        "press" | "hotkey" => validate_key_command(command, object)?,
        "wait" => {
            let seconds = object.get("seconds").and_then(Value::as_f64).unwrap_or(1.0);
            if object
                .get("seconds")
                .is_some_and(|v| v.as_bool().is_some() || !v.is_number())
                || !(0.0..=60.0).contains(&seconds)
            {
                return Err(issue("bad_arg", "wait seconds must be 0-60"));
            }
        }
        "batch" => {
            if let Some(final_observe) = object.get("final_observe") {
                let final_observe = final_observe
                    .as_object()
                    .ok_or_else(|| issue("bad_arg", "final_observe must be an object"))?;
                if final_observe.keys().any(|key| key != "image") {
                    return Err(issue(
                        "bad_arg",
                        "final_observe accepts only the image argument",
                    ));
                }
                if final_observe
                    .get("image")
                    .is_some_and(|value| !value.is_boolean())
                {
                    return Err(issue("bad_arg", "final_observe.image must be a boolean"));
                }
            }
            if let Some(deadline) = object.get("deadline_ms") {
                let value = deadline
                    .as_f64()
                    .filter(|_| deadline.as_bool().is_none())
                    .ok_or_else(|| issue("bad_arg", "deadline_ms must be 0-600000"))?;
                if value <= 0.0 || value > 600_000.0 {
                    return Err(issue("bad_arg", "deadline_ms must be 0-600000"));
                }
            }
            preflight_batch(object)?;
        }
        _ => {}
    }

    if is_keyboard_command(command) {
        require_app(object)
            .map_err(|_| issue("focus_required", "keyboard input requires an app"))?;
    }
    if ["move", "type", "click_type"].contains(&command) {
        let timing = object
            .get("timing")
            .and_then(Value::as_str)
            .unwrap_or("native");
        if !["human", "compatibility", "native"].contains(&timing) {
            return Err(issue(
                "bad_arg",
                format!("unknown timing mode: {timing} (use human, compatibility, native)"),
            ));
        }
    }
    if is_input_command(command) {
        return confirmation(
            object,
            object.get("text").and_then(Value::as_str).unwrap_or(""),
        );
    }
    Ok(())
}

fn allowed(command: &str) -> &'static [&'static str] {
    match command {
        "observe" => &["region", "metadata_only", "path_mode"],
        "list_apps" | "active-window" | "stop" | "doctor" => &[],
        "list_windows" | "focus_app" | "launch" => &["app"],
        "move" => &["x", "y", "frame_id", "seed", "timing", "risk", "confirm"],
        "click" | "double-click" | "right_click" => &["x", "y", "frame_id", "risk", "confirm"],
        "drag" => &[
            "from_x", "from_y", "to_x", "to_y", "frame_id", "seed", "risk", "confirm",
        ],
        "scroll" => &["direction", "amount", "risk", "confirm"],
        "type" => &["text", "app", "timing", "verify", "risk", "confirm"],
        "click_type" => &[
            "text", "app", "x", "y", "frame_id", "timing", "verify", "risk", "confirm",
        ],
        "press" | "hotkey" => &["keys", "app", "verify", "risk", "confirm"],
        "wait" => &["seconds"],
        "batch" => &[
            "actions",
            "deadline_ms",
            "app",
            "risk",
            "confirm",
            "final_observe",
        ],
        _ => &[],
    }
}

fn validate_fields(command: &str, params: &Map<String, Value>) -> Result<(), ValidationError> {
    let unknown: Vec<_> = params
        .keys()
        .filter(|key| !allowed(command).contains(&key.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        let hints = unknown
            .iter()
            .filter_map(|key| match (command, key.as_str()) {
                (_, "target") => Some("did you mean 'app'? keyboard input needs 'app'"),
                ("press" | "hotkey", "text") => {
                    Some("press/hotkey take 'keys' (e.g. 'enter', 'cmd,space'), not 'text'")
                }
                ("press" | "hotkey", "key_name") => {
                    Some("use 'keys' as one string, not 'key_name' or a list")
                }
                ("type" | "click_type", "keys") => Some("type/click_type take 'text', not 'keys'"),
                (_, "frame-id") => Some("use 'frame_id' with an underscore"),
                _ => None,
            })
            .collect::<Vec<_>>();
        let hint = if hints.is_empty() {
            String::new()
        } else {
            format!(" {}", hints.join(" "))
        };
        return Err(issue(
            "bad_arg",
            format!("unknown argument(s): {}.{hint}", unknown.join(", ")),
        ));
    }
    Ok(())
}

fn validate_common(params: &Map<String, Value>) -> Result<(), ValidationError> {
    if params.get("app").is_some_and(|v| !v.is_string()) {
        return Err(issue("bad_arg", "app must be a string"));
    }
    if params
        .get("frame_id")
        .is_some_and(|v| v.as_str().is_none_or(str::is_empty))
    {
        return Err(issue("bad_arg", "frame_id must be a non-empty string"));
    }
    if params
        .get("seed")
        .is_some_and(|v| v.as_i64().is_none() || v.as_bool().is_some())
    {
        return Err(issue("bad_arg", "seed must be an integer"));
    }
    if params
        .get("verify")
        .is_some_and(|v| !["focus", "effect"].contains(&v.as_str().unwrap_or("")))
    {
        return Err(issue("bad_arg", "verify must be focus or effect"));
    }
    Ok(())
}

fn require_app(params: &Map<String, Value>) -> Result<(), ValidationError> {
    if params
        .get("app")
        .and_then(Value::as_str)
        .is_none_or(|app| app.trim().is_empty())
    {
        Err(issue("bad_arg", "app must be a non-empty application name"))
    } else {
        Ok(())
    }
}

fn require_integer(params: &Map<String, Value>, key: &str) -> Result<i64, ValidationError> {
    params
        .get(key)
        .and_then(Value::as_i64)
        .filter(|_| params.get(key).and_then(Value::as_bool).is_none())
        .ok_or_else(|| issue("bad_arg", format!("{key} must be an integer")))
}

fn parse_region(text: &str) -> Result<(i64, i64, i64, i64), ValidationError> {
    if text.trim().is_empty() {
        return Ok((0, 0, 0, 0));
    }
    let values: Result<Vec<i64>, _> = text
        .split(',')
        .map(|part| part.trim().parse::<i64>())
        .collect();
    let values = values.map_err(|_| issue("bad_arg", "region must be x,y,w,h integers"))?;
    if values.len() != 4 {
        return Err(issue("bad_arg", "region must be x,y,w,h integers"));
    }
    if values[2] <= 0 || values[3] <= 0 {
        return Err(issue("bad_arg", "region width/height must be positive"));
    }
    Ok((values[0], values[1], values[2], values[3]))
}

fn validate_text(text: &str) -> Result<(), ValidationError> {
    if text.is_empty() {
        return Err(issue("bad_arg", "text must be a non-empty string"));
    }
    if text.contains('\0') {
        return Err(issue("bad_arg", "text must not contain NUL characters"));
    }
    if text.chars().count() > MAX_TEXT {
        return Err(issue(
            "bad_arg",
            format!("text exceeds {MAX_TEXT} characters"),
        ));
    }
    Ok(())
}

const CHALLENGE_HINTS: &[&str] = &[
    "password",
    "permission",
    "payment",
    "captcha",
    "turnstile",
    "verify you are human",
];
const RISK_HINTS: &[&str] = &[
    "delete", "remove", "purchase", "buy", "checkout", "pay", "send", "publish", "post", "submit",
    "confirm",
];

fn looks_like_challenge(text: &str) -> bool {
    let text = text.to_lowercase();
    CHALLENGE_HINTS.iter().any(|hint| text.contains(hint))
}

fn confirmation(params: &Map<String, Value>, text: &str) -> Result<(), ValidationError> {
    let risk = params
        .get("risk")
        .and_then(Value::as_str)
        .ok_or_else(|| issue("bad_arg", "input requires an explicit risk classification"))?;
    const RISKS: &[&str] = &[
        "none",
        "deletion",
        "purchase",
        "message",
        "publishing",
        "permission",
        "account_security",
    ];
    if !RISKS.contains(&risk) {
        return Err(issue(
            "bad_arg",
            "risk must be one of: account_security, deletion, message, permission, publishing, purchase, none",
        ));
    }
    if params.get("confirm").is_some_and(|v| !v.is_boolean()) {
        return Err(issue("bad_arg", "confirm must be a boolean"));
    }
    if (risk != "none"
        || RISK_HINTS
            .iter()
            .any(|hint| text.to_lowercase().contains(hint)))
        && params.get("confirm") != Some(&Value::Bool(true))
    {
        return Err(issue(
            "needs_attention",
            "consequential input requires fresh confirmation with confirm: true",
        ));
    }
    Ok(())
}

fn validate_key_command(command: &str, params: &Map<String, Value>) -> Result<(), ValidationError> {
    let source = params.get("keys").and_then(Value::as_str).ok_or_else(|| {
        issue(
            "bad_arg",
            "keys must be a string like 'enter' or 'cmd,space', not a list",
        )
    })?;
    let parts = key_parts(source);
    if parts.is_empty() {
        return Err(issue("bad_arg", "keys required"));
    }
    const MODS: &[&str] = &["cmd", "shift", "option", "alt", "ctrl", "control", "win"];
    const KEY_NAMES: &[&str] = &[
        "return",
        "enter",
        "escape",
        "esc",
        "tab",
        "space",
        "delete",
        "backspace",
        "forward_delete",
        "up",
        "down",
        "left",
        "right",
        "home",
        "end",
        "pageup",
        "pagedown",
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
        "f6",
        "f7",
        "f8",
        "f9",
        "f10",
        "f11",
        "f12",
    ];
    for part in &parts {
        let single = part.len() == 1 && part.as_bytes()[0].is_ascii_alphanumeric();
        if !MODS.contains(&part.as_str()) && !KEY_NAMES.contains(&part.as_str()) && !single {
            return Err(issue("bad_arg", format!("unknown key: {part}")));
        }
    }
    let regular: Vec<_> = parts
        .iter()
        .filter(|part| !MODS.contains(&part.as_str()))
        .collect();
    let canonical: Vec<_> = parts
        .iter()
        .map(|part| match part.as_str() {
            "command" => "cmd",
            "control" => "ctrl",
            "option" => "alt",
            _ => part.as_str(),
        })
        .collect();
    if canonical == ["cmd", "shift", "q"]
        || canonical == ["win", "l"]
        || canonical == ["ctrl", "alt", "delete"]
        || canonical == ["alt", "f4"]
    {
        return Err(issue("blocked", "key combo blocked for safety"));
    }
    if regular.len() != 1 {
        return Err(issue(
            "bad_arg",
            "key input requires exactly one non-modifier key",
        ));
    }
    if command == "press" && parts.len() != 1 {
        return Err(issue(
            "bad_arg",
            "press accepts one non-modifier key; use hotkey for modifiers",
        ));
    }
    Ok(())
}

fn key_parts(keys: &str) -> Vec<String> {
    let raw: Vec<String> = keys
        .replace(['-', ','], "+")
        .split('+')
        .map(|part| part.trim().to_lowercase())
        .filter(|part| !part.is_empty())
        .collect();
    let aliases = [("command", "cmd"), ("control", "ctrl"), ("option", "alt")];
    let mut modifiers = BTreeSet::new();
    let mut ordinary = Vec::new();
    for part in raw {
        let normalized = aliases
            .iter()
            .find_map(|(alias, target)| (part == *alias).then_some(*target))
            .unwrap_or(&part);
        if ["cmd", "ctrl", "alt", "shift", "win"].contains(&normalized) {
            modifiers.insert(normalized.to_string());
        } else {
            ordinary.push(normalized.to_string());
        }
    }
    let mut result = Vec::new();
    for modifier in ["cmd", "ctrl", "alt", "shift", "win"] {
        if modifiers.contains(modifier) {
            result.push(modifier.to_owned());
        }
    }
    result.extend(ordinary);
    result
}

pub fn canonical_keys(keys: &str) -> String {
    key_parts(keys).join(",")
}

fn preflight_batch(params: &Map<String, Value>) -> Result<(), ValidationError> {
    if let Some(app) = params.get("app")
        && app.as_str().is_none_or(|value| value.trim().is_empty())
    {
        return Err(issue("bad_arg", "batch app must be a non-empty string"));
    }
    let actions = params
        .get("actions")
        .and_then(Value::as_array)
        .ok_or_else(|| issue("bad_arg", "actions must be a list"))?;
    if actions.is_empty() {
        return Err(issue("bad_arg", "empty batch"));
    }
    let count = action_count(actions);
    if count > MAX_BATCH_ACTIONS {
        return Err(issue(
            "bad_arg",
            format!("too many actions: maximum is {MAX_BATCH_ACTIONS}"),
        ));
    }
    let batch_app = params.get("app").and_then(Value::as_str).unwrap_or("");
    for (index, action) in actions.iter().enumerate() {
        let action = action
            .as_object()
            .ok_or_else(|| issue("bad_arg", format!("action {index}: unknown op")))?;
        let op = action
            .get("op")
            .and_then(Value::as_str)
            .filter(|op| crate::protocol::COMMANDS.contains(op))
            .ok_or_else(|| issue("bad_arg", format!("action {index}: unknown op")))?;
        if op == "stop" {
            return Err(issue(
                "bad_arg",
                format!("action {index}: stop cannot be batched"),
            ));
        }
        if op == "observe" && action.get("metadata_only") != Some(&Value::Bool(true)) {
            return Err(issue(
                "bad_arg",
                format!("action {index}: batch observe requires metadata_only"),
            ));
        }
        let mut effective = action.clone();
        effective.remove("op");
        if is_input_command(op) || op == "batch" {
            if !effective.contains_key("risk")
                && let Some(risk) = params.get("risk")
            {
                effective.insert("risk".into(), risk.clone());
            }
            if !effective.contains_key("confirm")
                && let Some(confirm) = params.get("confirm")
            {
                effective.insert("confirm".into(), confirm.clone());
            }
        }
        if is_keyboard_command(op) && !effective.contains_key("app") && !batch_app.is_empty() {
            effective.insert("app".into(), Value::String(batch_app.to_owned()));
        }
        if op == "batch" && !effective.contains_key("app") && !batch_app.is_empty() {
            effective.insert("app".into(), Value::String(batch_app.to_owned()));
        }
        preflight(op, &Value::Object(effective))
            .map_err(|error| issue(error.code, format!("action {index}: {}", error.message)))?;
    }
    Ok(())
}

fn action_count(actions: &[Value]) -> usize {
    actions
        .iter()
        .map(|action| {
            let list = action.get("actions").and_then(Value::as_array);
            1 + if action.get("op").and_then(Value::as_str) == Some("batch") {
                list.map_or(0, |items| action_count(items))
            } else {
                0
            }
        })
        .sum()
}
