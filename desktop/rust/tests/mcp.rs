use computer_automation::MockBackend;
use serde_json::Value;
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Command, Stdio};
use std::sync::Arc;

#[test]
fn stdio_methods_preserve_mcp_version_tools_and_command_envelopes() {
    let server = computer_automation::mcp::McpServer::new(MockBackend, true);
    let initialized: Value = serde_json::from_str(
        &server
            .handle_line(r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}"#)
            .unwrap(),
    )
    .unwrap();
    assert_eq!(initialized["result"]["protocolVersion"], "2026-07-28");

    let tools: Value = serde_json::from_str(
        &server
            .handle_line(r#"{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}"#)
            .unwrap(),
    )
    .unwrap();
    let commands = tools["result"]["tools"][0]["inputSchema"]["properties"]["command"]["enum"]
        .as_array()
        .unwrap();
    assert_eq!(commands.len(), 20);

    let called: Value = serde_json::from_str(
        &server
            .handle_line(
                r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"desktop","arguments":{"command":"click","params":{"x":5,"y":6,"risk":"none"}}}}"#,
            )
            .unwrap(),
    )
    .unwrap();
    let text = called["result"]["content"][0]["text"].as_str().unwrap();
    let envelope: Value = serde_json::from_str(text).unwrap();
    assert_eq!(envelope["data"]["dry_run"], true);
    assert_eq!(called["result"]["isError"], false);

    let live_server = computer_automation::mcp::McpServer::new(MockBackend, false);
    let batch: Value = serde_json::from_str(
        &live_server
            .handle_line(
                r#"{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"desktop","arguments":{"command":"batch","params":{"actions":[{"op":"wait","seconds":0}],"final_observe":{"image":true}}}}}"#,
            )
            .unwrap(),
    )
    .unwrap();
    assert_eq!(batch["result"]["content"].as_array().unwrap().len(), 2);
    let batch_envelope: Value =
        serde_json::from_str(batch["result"]["content"][0]["text"].as_str().unwrap()).unwrap();
    assert_eq!(batch_envelope["ok"], true);
    assert_eq!(batch_envelope["data"]["final_observation"]["ok"], true);
    assert_eq!(batch["result"]["content"][1]["type"], "image");
    assert_eq!(batch["result"]["content"][1]["mimeType"], "image/png");
}

#[test]
fn cancellation_notifications_remain_out_of_band_and_match_request_ids() {
    let server = Arc::new(computer_automation::mcp::McpServer::new(MockBackend, false));
    std::thread::scope(|scope| {
        let request_server = Arc::clone(&server);
        let worker = scope.spawn(move || {
            request_server.handle_line(
                r#"{"jsonrpc":"2.0","id":51,"method":"tools/call","params":{"name":"desktop","arguments":{"command":"wait","params":{"seconds":10}}}}"#,
            )
        });
        std::thread::sleep(std::time::Duration::from_millis(20));
        assert!(server
            .handle_line(r#"{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":52}}"#)
            .is_none());
        assert!(server
            .handle_line(r#"{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":51,"generation":2}}"#)
            .is_none());
        assert!(server
            .handle_line(r#"{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":51,"generation":1}}"#)
            .is_none());
        let response: Value = serde_json::from_str(&worker.join().unwrap().unwrap()).unwrap();
        let envelope: Value =
            serde_json::from_str(response["result"]["content"][0]["text"].as_str().unwrap())
                .unwrap();
        assert_eq!(envelope["error"]["code"], "cancelled");
    });
}

#[test]
fn mcp_binary_serves_newline_delimited_stdio_requests() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_computer-mcp"))
        .env("DESKTOP_FAKE_BACKEND", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("start MCP binary");
    let input = child.stdin.as_mut().unwrap();
    input
        .write_all(
            concat!(
                "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}\n",
                "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\",\"params\":{}}\n",
                "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"desktop\",\"arguments\":{\"command\":\"click\",\"params\":{\"x\":5,\"y\":6,\"risk\":\"none\"}}}}\n"
            )
            .as_bytes(),
        )
        .unwrap();
    drop(child.stdin.take());
    let output = child.wait_with_output().expect("wait for MCP server");
    assert_eq!(output.status.code(), Some(0));
    let responses: Vec<Value> = String::from_utf8(output.stdout)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert_eq!(responses.len(), 3);
    assert!(responses.iter().any(|response| response["id"] == 1));
    assert!(responses.iter().any(|response| response["id"] == 2));
    assert!(responses.iter().any(|response| response["id"] == 3));
}

#[test]
fn mcp_stdio_reader_handles_cancel_notifications_during_a_wait() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_computer-mcp"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("start MCP binary");
    let mut input = child.stdin.take().unwrap();
    let mut output = BufReader::new(child.stdout.take().unwrap());
    input
        .write_all(b"{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}\n")
        .unwrap();
    let mut line = String::new();
    output.read_line(&mut line).unwrap();
    assert!(line.contains("initialize") || line.contains("protocolVersion"));

    input
        .write_all(
            b"{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"desktop\",\"arguments\":{\"command\":\"wait\",\"params\":{\"seconds\":10}}}}\n",
        )
        .unwrap();
    input
        .write_all(b"{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"ping\",\"params\":{}}\n")
        .unwrap();
    line.clear();
    output.read_line(&mut line).unwrap();
    assert!(line.contains("\"id\":3"));
    std::thread::sleep(std::time::Duration::from_millis(30));
    input
        .write_all(b"{\"jsonrpc\":\"2.0\",\"method\":\"notifications/cancelled\",\"params\":{\"requestId\":2,\"generation\":1}}\n")
        .unwrap();
    drop(input);

    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
    while child.try_wait().unwrap().is_none() && std::time::Instant::now() < deadline {
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    if child.try_wait().unwrap().is_none() {
        child.kill().unwrap();
        panic!("cancellation did not stop the MCP wait");
    }
    let mut remaining = String::new();
    output.read_to_string(&mut remaining).unwrap();
    let responses: Vec<Value> = remaining
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    let wait = responses
        .iter()
        .find(|response| response["id"] == 2)
        .unwrap();
    let envelope: Value =
        serde_json::from_str(wait["result"]["content"][0]["text"].as_str().unwrap()).unwrap();
    assert_eq!(envelope["error"]["code"], "cancelled");
}
