use computer_automation::{MockBackend, NativeBackend};
use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args == ["--help"] || args == ["-h"] {
        println!(
            "computer-mcp: local newline-delimited JSON-RPC/MCP stdio server over stdin/stdout; send initialize, ping, tools/list, or tools/call"
        );
        return ExitCode::SUCCESS;
    }
    if !args.is_empty() {
        eprintln!("computer-mcp accepts only --help; protocol traffic uses stdio");
        return ExitCode::from(2);
    }
    let result = if std::env::var("DESKTOP_FAKE_BACKEND").as_deref() == Ok("1") {
        computer_automation::mcp::run_stdio(MockBackend, false)
    } else {
        computer_automation::mcp::run_stdio(NativeBackend::current(), false)
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("computer-mcp stdio failure: {error}");
            ExitCode::from(5)
        }
    }
}
