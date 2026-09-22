use serde_json::{Map, Number, Value, json};

pub enum CliOutcome {
    Help,
    Version,
    Command {
        execute: bool,
        name: String,
        params: Value,
    },
    Error(Value),
}

const COMMAND_USAGE: &[&str] = &[
    "observe [--region X,Y,W,H] [--metadata-only] [--to-file]",
    "list_apps",
    "list_windows [--app APP]",
    "active-window",
    "focus_app --app APP",
    "launch --app APP",
    "move --x X --y Y [--seed N] [--timing MODE] --risk RISK [--confirm]",
    "click --x X --y Y [--frame-id ID] --risk RISK [--confirm]",
    "double-click --x X --y Y [--frame-id ID] --risk RISK [--confirm]",
    "right_click --x X --y Y [--frame-id ID] --risk RISK [--confirm]",
    "drag --from X,Y --to X,Y [--frame-id ID] --risk RISK [--confirm]",
    "scroll [--direction DIR] [--amount N] --risk RISK [--confirm]",
    "type TEXT [--app APP] [--timing MODE] --risk RISK [--confirm]",
    "click_type TEXT --app APP --x X --y Y [--frame-id ID] --risk RISK [--confirm]",
    "press KEYS [--app APP] --risk RISK [--confirm]",
    "hotkey KEYS [--app APP] --risk RISK [--confirm]",
    "wait [--seconds N]",
    "batch --json JSON",
    "stop",
    "doctor",
];

pub fn parse(args: &[String]) -> CliOutcome {
    let (execute, words) = match normalize_flags(args) {
        Ok(normalized) => normalized,
        Err(()) => return usage_error("argument --dry-run: not allowed with argument --execute"),
    };
    let command_words: Vec<_> = words
        .iter()
        .take_while(|word| word.as_str() != "--")
        .collect();
    if command_words
        .iter()
        .any(|word| word.as_str() == "--help" || word.as_str() == "-h")
    {
        return CliOutcome::Help;
    }
    if command_words
        .iter()
        .any(|word| word.as_str() == "--version")
    {
        return CliOutcome::Version;
    }
    let Some(command) = words.first().map(String::as_str) else {
        return usage_error("a command is required");
    };
    if !crate::protocol::COMMANDS.contains(&command) {
        return usage_error(format!("unknown command: {command}"));
    }
    let mut params = Map::new();
    let mut positionals = Vec::new();
    let mut index = 1;
    let mut literal = false;
    while index < words.len() {
        let word = &words[index];
        if literal {
            positionals.push(word.clone());
            index += 1;
            continue;
        }
        if word == "--" {
            literal = true;
            index += 1;
            continue;
        }
        if !word.starts_with('-') {
            positionals.push(word.clone());
            index += 1;
            continue;
        }
        let (raw_key, inline_value) = word
            .strip_prefix("--")
            .unwrap_or(word)
            .split_once('=')
            .map_or((word.strip_prefix("--").unwrap_or(word), None), |(k, v)| {
                (k, Some(v))
            });
        let key = match raw_key {
            "frame-id" => "frame_id",
            "metadata-only" => "metadata_only",
            "to-file" => "path_mode",
            "from" => "from",
            _ => raw_key,
        };
        if matches!(key, "confirm" | "metadata_only" | "path_mode") {
            params.insert(key.to_owned(), Value::Bool(true));
            index += 1;
            continue;
        }
        let value = if let Some(value) = inline_value {
            value.to_owned()
        } else if let Some(value) = words.get(index + 1) {
            index += 1;
            value.clone()
        } else {
            return usage_error(format!("argument --{raw_key} requires a value"));
        };
        let parsed = match key {
            "x" | "y" | "seed" | "amount" | "from" | "to" => Value::String(value),
            "seconds" => match value.parse::<f64>() {
                Ok(number) if number.is_finite() => json!(number),
                _ => return usage_error(format!("argument --{raw_key}: invalid float value")),
            },
            _ => Value::String(value),
        };
        params.insert(key.to_owned(), parsed);
        index += 1;
    }
    if let Err(error) = apply_defaults_and_positionals(command, &mut params, &positionals) {
        return usage_error(error);
    }
    let mut normalized = Map::new();
    for (key, value) in params {
        let converted = match key.as_str() {
            "x" | "y" | "seed" | "amount" => {
                match value
                    .as_i64()
                    .or_else(|| value.as_str().and_then(|s| s.parse::<i64>().ok()))
                {
                    Some(number) => Value::Number(Number::from(number)),
                    None => return usage_error(format!("argument --{key}: invalid integer value")),
                }
            }
            "from" | "to" => match parse_pair(value.as_str().unwrap_or("")) {
                Some(pair) => {
                    normalized.insert(
                        if key == "from" { "from_x" } else { "to_x" }.to_owned(),
                        json!(pair.0),
                    );
                    normalized.insert(
                        if key == "from" { "from_y" } else { "to_y" }.to_owned(),
                        json!(pair.1),
                    );
                    continue;
                }
                None => return usage_error("drag coords must be x,y"),
            },
            _ => value,
        };
        normalized.insert(key, converted);
    }
    if crate::validation::is_input_command(command) {
        normalized.entry("risk").or_insert(Value::Null);
        normalized.entry("confirm").or_insert(Value::Bool(false));
    }
    CliOutcome::Command {
        execute,
        name: command.to_owned(),
        params: Value::Object(normalized),
    }
}

fn apply_defaults_and_positionals(
    command: &str,
    params: &mut Map<String, Value>,
    positionals: &[String],
) -> Result<(), String> {
    let positional_key = match command {
        "type" | "click_type" => Some("text"),
        "press" | "hotkey" => Some("keys"),
        _ => None,
    };
    if let Some(key) = positional_key {
        if positionals.len() != 1 {
            return Err(format!("{command} requires one argument"));
        }
        params.insert(key.into(), Value::String(positionals[0].clone()));
    } else if !positionals.is_empty() {
        return Err(format!("unexpected argument: {}", positionals[0]));
    }
    for (key, value) in [
        ("region", json!("")),
        ("metadata_only", json!(false)),
        ("path_mode", json!(false)),
        ("direction", json!("down")),
        ("amount", json!(3)),
        ("seconds", json!(1.0)),
        ("timing", json!("native")),
        ("seed", json!(0)),
        ("app", json!("")),
    ] {
        let applies = match key {
            "region" | "metadata_only" | "path_mode" => command == "observe",
            "direction" | "amount" => command == "scroll",
            "seconds" => command == "wait",
            "timing" => matches!(command, "move" | "type" | "click_type"),
            "seed" => command == "move",
            "app" => matches!(command, "type" | "click_type" | "press" | "hotkey"),
            _ => false,
        };
        if applies {
            params.entry(key).or_insert(value);
        }
    }
    let required = match command {
        "focus_app" | "launch" => &["app"][..],
        "move" | "click" | "double-click" | "right_click" => &["x", "y"][..],
        "click_type" => &["app", "x", "y", "text"][..],
        "drag" => &["from", "to"][..],
        "batch" => &["json"][..],
        "type" => &["text"][..],
        "press" | "hotkey" => &["keys"][..],
        _ => &[][..],
    };
    for key in required {
        if !params.contains_key(*key) {
            return Err(format!("the following arguments are required: --{key}"));
        }
    }
    if command == "batch" {
        let raw = params
            .remove("json")
            .ok_or_else(|| "the following arguments are required: --json".to_owned())?;
        let spec: Value = serde_json::from_str(raw.as_str().unwrap_or(""))
            .map_err(|error| format!("invalid batch JSON: {error}"))?;
        let spec = spec
            .as_object()
            .ok_or_else(|| "batch JSON must be an object".to_owned())?;
        *params = spec.clone();
    }
    Ok(())
}

fn normalize_flags(args: &[String]) -> Result<(bool, Vec<String>), ()> {
    let mut execute = false;
    let mut selected = None;
    let mut words = Vec::new();
    let mut literal = false;
    for arg in args {
        if !literal && arg == "--" {
            literal = true;
            words.push(arg.clone());
        } else if !literal && arg == "--execute" {
            execute = true;
            if selected == Some(false) {
                return Err(());
            }
            selected = Some(true);
        } else if !literal && arg == "--dry-run" {
            execute = false;
            if selected == Some(true) {
                return Err(());
            }
            selected = Some(false);
        } else {
            words.push(arg.clone());
        }
    }
    Ok((execute, words))
}

fn parse_pair(value: &str) -> Option<(i64, i64)> {
    let (x, y) = value.split_once(',')?;
    Some((x.trim().parse().ok()?, y.trim().parse().ok()?))
}

fn usage_error(message: impl Into<String>) -> CliOutcome {
    CliOutcome::Error(crate::protocol::fail(
        "bad_arg",
        &message.into(),
        "run desktop --help for valid arguments",
    ))
}

pub fn help() -> String {
    format!(
        "desktop {}\nOS-level desktop control. Real OS input only. Dry-run is the default; pass --execute to act.\n\nCommands:\n  {}\n",
        env!("CARGO_PKG_VERSION"),
        COMMAND_USAGE.join("\n  ")
    )
}

#[cfg(test)]
mod tests {
    use super::{CliOutcome, parse};

    fn args(words: &[&str]) -> Vec<String> {
        words.iter().map(|word| (*word).to_owned()).collect()
    }

    #[test]
    fn dry_run_defaults_and_normalizes_public_input_arguments() {
        let CliOutcome::Error(conflict) = parse(&args(&["--execute", "--dry-run", "click"])) else {
            panic!("mutually exclusive flags must be rejected")
        };
        assert_eq!(conflict["error"]["code"], "bad_arg");

        let CliOutcome::Command {
            execute,
            name,
            params,
        } = parse(&args(&["click", "--x", "-5", "--y", "4", "--risk", "none"]))
        else {
            panic!("expected a command")
        };
        assert!(!execute);
        assert_eq!(name, "click");
        assert_eq!(
            params,
            serde_json::json!({"x":-5,"y":4,"risk":"none","confirm":false})
        );

        let CliOutcome::Command { params, .. } =
            parse(&args(&["move", "--x", "10", "--y", "20", "--risk", "none"]))
        else {
            panic!("expected move with a numeric default seed")
        };
        assert_eq!(params["seed"], 0);

        let CliOutcome::Command { params, .. } = parse(&args(&["scroll", "--risk", "none"])) else {
            panic!("expected scroll with a numeric default amount")
        };
        assert_eq!(params["amount"], 3);
    }

    #[test]
    fn maps_batch_json_and_drag_coordinates() {
        let CliOutcome::Command { params, .. } = parse(&args(&[
            "batch",
            "--json",
            r#"{"actions":[{"op":"wait","seconds":0}]}"#,
        ])) else {
            panic!("expected a command")
        };
        assert_eq!(params["actions"][0]["op"], "wait");

        let CliOutcome::Command { params, .. } = parse(&args(&[
            "drag", "--from", "1,2", "--to", "3,4", "--risk", "none",
        ])) else {
            panic!("expected a command")
        };
        assert_eq!(params["from_x"], 1);
        assert_eq!(params["to_y"], 4);
    }

    #[test]
    fn preserves_literal_global_flag_after_separator() {
        let CliOutcome::Command { params, .. } = parse(&args(&[
            "type",
            "--app",
            "Finder",
            "--risk",
            "none",
            "--",
            "--execute",
        ])) else {
            panic!("expected a command")
        };
        assert_eq!(params["text"], "--execute");

        let CliOutcome::Command { params, .. } = parse(&args(&[
            "type", "--app", "Finder", "--risk", "none", "--", "--help",
        ])) else {
            panic!("expected a command")
        };
        assert_eq!(params["text"], "--help");
    }
}
