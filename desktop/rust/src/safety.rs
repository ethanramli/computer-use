use serde_json::Value;

pub struct SafetyIssue {
    pub code: &'static str,
    pub message: &'static str,
}

pub fn input_state_issue(state: &Value) -> Option<SafetyIssue> {
    let Some(state) = state.as_object().filter(|state| !state.is_empty()) else {
        return Some(unknown());
    };
    const FLAGS: &[&str] = &["secure", "payment", "permission", "challenge"];
    if FLAGS
        .iter()
        .any(|flag| state.get(*flag) == Some(&Value::Bool(true)))
    {
        return Some(sensitive());
    }
    let searchable = state
        .values()
        .filter_map(Value::as_str)
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase();
    let has_explicit_flags = FLAGS
        .iter()
        .any(|flag| state.get(*flag).is_some_and(Value::is_boolean));
    if searchable.trim().is_empty() && !has_explicit_flags {
        return Some(unknown());
    }
    const HINTS: &[&str] = &[
        "password",
        "permission",
        "payment",
        "captcha",
        "turnstile",
        "verify you are human",
        "securetextfield",
        "credit card",
        "card number",
        "security code",
        "passcode",
        "two-factor",
        "two factor",
        "authentication",
        "axdialog",
        "axsystemdialog",
    ];
    HINTS
        .iter()
        .any(|hint| searchable.contains(hint))
        .then(sensitive)
}

fn unknown() -> SafetyIssue {
    SafetyIssue {
        code: "needs_attention",
        message: "input safety state could not be inspected",
    }
}

fn sensitive() -> SafetyIssue {
    SafetyIssue {
        code: "needs_attention",
        message: "secure or challenge UI is focused",
    }
}
