use computer_automation::{Controller, DesktopBackend, MockBackend, NativeBackend};
use serde_json::Value;
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match computer_automation::cli::parse(&args) {
        computer_automation::cli::CliOutcome::Help => {
            print!("{}", computer_automation::cli::help());
            ExitCode::SUCCESS
        }
        computer_automation::cli::CliOutcome::Version => {
            println!("desktop {}", env!("CARGO_PKG_VERSION"));
            ExitCode::SUCCESS
        }
        computer_automation::cli::CliOutcome::Error(envelope) => output(envelope),
        computer_automation::cli::CliOutcome::Command {
            execute,
            name,
            params,
        } => {
            if name == "stop" {
                return output(computer_automation::protocol::ok(serde_json::json!({
                    "stopped": false,
                    "reason": "one-shot CLI has no persistent work to cancel",
                    "recover": "send notifications/cancelled with the active requestId to the running computer-mcp process"
                })));
            }
            if execute
                && [
                    "move",
                    "click",
                    "double-click",
                    "right_click",
                    "drag",
                    "click_type",
                ]
                .contains(&name.as_str())
            {
                return output(computer_automation::protocol::fail(
                    "unsupported",
                    "one-shot CLI coordinate input cannot reuse an observed frame",
                    "use one persistent computer-mcp session for observe then coordinate input",
                ));
            }
            if execute && name == "observe" && params["path_mode"] == true {
                return output(computer_automation::protocol::fail(
                    "unsupported",
                    "one-shot path mode would expire when the process exits",
                    "use observe path_mode in a persistent computer-mcp session",
                ));
            }
            if std::env::var("DESKTOP_FAKE_BACKEND").as_deref() == Ok("1") {
                run_command(MockBackend, execute, &name, &params)
            } else {
                run_command(NativeBackend::current(), execute, &name, &params)
            }
        }
    }
}

fn run_command<B: DesktopBackend>(
    backend: B,
    execute: bool,
    name: &str,
    params: &Value,
) -> ExitCode {
    let mut controller = Controller::new(backend, !execute);
    output(controller.command(name, params))
}

fn output(envelope: Value) -> ExitCode {
    println!("{envelope}");
    if envelope["ok"] == true {
        return ExitCode::SUCCESS;
    }
    let code = match envelope["error"]["code"].as_str().unwrap_or("") {
        "bad_arg" => 2,
        "needs_attention" | "focus_required" => 3,
        "blocked" | "unsupported" | "unimplemented" => 4,
        _ => 5,
    };
    ExitCode::from(code)
}
