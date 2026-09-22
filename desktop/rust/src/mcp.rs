use crate::{CancellationHandle, Controller, DesktopBackend, protocol};
use serde_json::{Map, Value, json};
use std::io::{self, BufRead, BufReader, Write};
use std::sync::mpsc::{TrySendError, sync_channel};
use std::sync::{Arc, Mutex};
use std::thread;

pub const PROTOCOL_VERSION: &str = "2026-07-28";
pub const MAX_MESSAGE_BYTES: usize = 4 * 1024 * 1024;

pub struct McpServer<B: DesktopBackend> {
    controller: Mutex<Controller<B>>,
    cancellation: CancellationHandle,
}

impl<B: DesktopBackend> McpServer<B> {
    pub fn new(backend: B, dry_run: bool) -> Self {
        let controller = Controller::new(backend, dry_run);
        let cancellation = controller.cancellation_handle();
        Self {
            controller: Mutex::new(controller),
            cancellation,
        }
    }

    pub fn handle_line(&self, line: &str) -> Option<String> {
        if line.len() > MAX_MESSAGE_BYTES {
            return Some(error(None, -32700, "message too large"));
        }
        let request: Value = match serde_json::from_str(line) {
            Ok(request) => request,
            Err(_) => return Some(error(None, -32700, "parse error")),
        };
        let Some(object) = request.as_object() else {
            return Some(error(None, -32600, "invalid request"));
        };
        let id_present = object.contains_key("id");
        let id = object.get("id").cloned().unwrap_or(Value::Null);
        if object.get("jsonrpc").and_then(Value::as_str) != Some("2.0") {
            return Some(error(None, -32600, "invalid request"));
        }
        if id_present && !valid_id(&id) {
            return Some(error(None, -32600, "invalid request id"));
        }
        let Some(method) = object.get("method").and_then(Value::as_str) else {
            return Some(error(
                id_present.then_some(id),
                -32600,
                "method must be a string",
            ));
        };
        let params = object.get("params").cloned().unwrap_or_else(|| json!({}));
        if method == "notifications/cancelled" {
            if let Some(request_id) = params.get("requestId")
                && let Some(generation) = parse_generation(params.get("generation"))
            {
                self.cancellation.cancel_request(request_id, generation);
            }
            return None;
        }
        if method.starts_with("notifications/") || !id_present {
            return None;
        }
        let Some(params) = params.as_object() else {
            return Some(error(Some(id), -32602, "params must be an object"));
        };
        let result = match method {
            "initialize" => Ok(json!({
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "computer-mcp", "version": env!("CARGO_PKG_VERSION")}
            })),
            "ping" => Ok(json!({})),
            "tools/list" => Ok(json!({"tools": [tool_definition()]})),
            "tools/call" => {
                return Some(match self.call_tool(params, id.clone()) {
                    Ok(result) => response(id, result),
                    Err((code, message)) => error(Some(id), code, &message),
                });
            }
            _ => Err((-32601, format!("method not found: {method}"))),
        };
        Some(match result {
            Ok(result) => json!({"jsonrpc":"2.0", "id": id, "result": result}).to_string(),
            Err((code, message)) => error(Some(id), code, &message),
        })
    }

    pub fn cancellation_handle(&self) -> CancellationHandle {
        self.cancellation.clone()
    }

    fn call_tool(
        &self,
        params: &Map<String, Value>,
        request_id: Value,
    ) -> Result<Value, (i64, String)> {
        if params.get("name").and_then(Value::as_str) != Some("desktop") {
            return Err((
                -32602,
                format!(
                    "unknown tool: {}",
                    params.get("name").unwrap_or(&Value::Null)
                ),
            ));
        }
        let arguments_value = params
            .get("arguments")
            .cloned()
            .unwrap_or_else(|| Value::Object(Map::new()));
        let Some(arguments) = arguments_value.as_object().cloned() else {
            return Err((-32602, "arguments must be an object".into()));
        };
        let size = serde_json::to_vec(&arguments).map_or(usize::MAX, |bytes| bytes.len());
        if size > MAX_MESSAGE_BYTES {
            return Ok(tool_result(protocol::fail(
                "bad_arg",
                &format!("arguments too large: exceeds {MAX_MESSAGE_BYTES} bytes"),
                "split the request or reduce text/payload size",
            )));
        }
        let Some(command) = arguments.get("command").and_then(Value::as_str) else {
            return Err((-32602, "arguments.command is required".into()));
        };
        let command_params = arguments
            .get("params")
            .cloned()
            .unwrap_or_else(|| Value::Object(Map::new()));
        if !command_params.is_object() {
            return Err((-32602, "arguments.params must be an object".into()));
        }
        let envelope = if command == "stop" {
            if let Err(issue) = crate::validation::preflight(command, &command_params) {
                protocol::fail(issue.code, &issue.message, "fix the command and retry")
            } else {
                protocol::ok(json!({"stopped": self.cancellation.cancel()}))
            }
        } else {
            self.controller
                .lock()
                .expect("controller lock poisoned")
                .command_with_request_id(command, &command_params, Some(request_id))
        };
        Ok(tool_result(envelope))
    }

    fn is_cancellation_line(&self, line: &str) -> bool {
        serde_json::from_str::<Value>(line).is_ok_and(|value| {
            value.get("jsonrpc").and_then(Value::as_str) == Some("2.0")
                && value.get("method").and_then(Value::as_str) == Some("notifications/cancelled")
        })
    }

    fn is_stop_line(&self, line: &str) -> bool {
        serde_json::from_str::<Value>(line).is_ok_and(|value| {
            value.get("jsonrpc").and_then(Value::as_str) == Some("2.0")
                && value.get("method").and_then(Value::as_str) == Some("tools/call")
                && value
                    .get("params")
                    .and_then(|params| params.get("name"))
                    .and_then(Value::as_str)
                    == Some("desktop")
                && value
                    .get("params")
                    .and_then(|params| params.get("arguments"))
                    .and_then(|arguments| arguments.get("command"))
                    .and_then(Value::as_str)
                    == Some("stop")
        })
    }
}

fn tool_definition() -> Value {
    json!({
        "name": "desktop",
        "description": "Run one of the 20 local desktop commands. Real input is preceded by visible seeded Bezier cursor movement. Coordinate actions require a fresh frame from this session. Keyboard actions require a verified app focus and inspected non-sensitive UI. Consequential actions require matching risk and fresh confirm:true. Batch actions are wholly preflighted; use final_observe:{image:true} for one final screenshot when supported.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type":"string", "enum":crate::protocol::COMMANDS},
                "params": {"type":"object", "description":"Command arguments use the same names and JSON shape as the desktop CLI. batch accepts actions, app, risk, confirm, deadline_ms, and final_observe."}
            },
            "required": ["command"]
        }
    })
}

fn valid_id(value: &Value) -> bool {
    value.is_null() || value.is_string() || value.is_number() && value.as_f64().is_some()
}

fn parse_generation(value: Option<&Value>) -> Option<Option<u64>> {
    match value {
        None => Some(None),
        Some(value) if value.as_u64().is_some() => Some(value.as_u64()),
        Some(value) if value.as_i64().is_some() => Some(Some(u64::MAX)),
        Some(_) => None,
    }
}

fn response(id: Value, result: Value) -> String {
    json!({"jsonrpc":"2.0", "id": id, "result": result}).to_string()
}

fn error(id: Option<Value>, code: i64, message: &str) -> String {
    json!({"jsonrpc":"2.0", "id": id.unwrap_or(Value::Null), "error":{"code":code,"message":message}}).to_string()
}

fn tool_result(mut envelope: Value) -> Value {
    let mut image = None;
    if let Some(data) = envelope.get_mut("data").and_then(Value::as_object_mut)
        && let Some(Value::String(encoded)) = data.remove("image_b64")
    {
        image = Some(encoded);
    }
    let mut content = vec![json!({"type":"text", "text":envelope.to_string()})];
    if let Some(data) = image {
        content.push(json!({"type":"image", "data":data, "mimeType":"image/png"}));
    }
    json!({
        "content": content,
        "isError": envelope.get("ok") != Some(&Value::Bool(true))
    })
}

fn write_line(output: &Mutex<impl Write>, line: &str) -> io::Result<()> {
    let mut output = output.lock().expect("stdout lock poisoned");
    output.write_all(line.as_bytes())?;
    output.write_all(b"\n")?;
    output.flush()
}

fn read_limited_line(reader: &mut impl BufRead) -> io::Result<Option<Result<String, ()>>> {
    let mut bytes = Vec::new();
    let mut oversized = false;
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            if bytes.is_empty() && !oversized {
                return Ok(None);
            }
            return Ok(Some(if oversized {
                Err(())
            } else {
                Ok(String::from_utf8_lossy(&bytes).into_owned())
            }));
        }
        let newline = available.iter().position(|byte| *byte == b'\n');
        let count = newline.map_or(available.len(), |index| index + 1);
        if !oversized {
            let payload_bytes = count - usize::from(newline.is_some());
            if bytes.len().saturating_add(payload_bytes) > MAX_MESSAGE_BYTES {
                bytes.clear();
                oversized = true;
            } else {
                bytes.extend_from_slice(&available[..count]);
            }
        }
        reader.consume(count);
        if newline.is_some() {
            return Ok(Some(if oversized {
                Err(())
            } else {
                Ok(String::from_utf8_lossy(&bytes)
                    .trim_end_matches('\n')
                    .to_owned())
            }));
        }
    }
}

pub fn run_stdio<B: DesktopBackend + Send + 'static>(backend: B, dry_run: bool) -> io::Result<()> {
    let server = Arc::new(McpServer::new(backend, dry_run));
    let output = Arc::new(Mutex::new(io::stdout()));
    let (sender, receiver) = sync_channel::<String>(1);
    let worker_server = Arc::clone(&server);
    let worker_output = Arc::clone(&output);
    let worker = thread::spawn(move || {
        while let Ok(line) = receiver.recv() {
            if let Some(response) = worker_server.handle_line(&line)
                && write_line(&worker_output, &response).is_err()
            {
                break;
            }
        }
    });

    let stdin = io::stdin();
    let mut reader = BufReader::new(stdin.lock());
    while let Some(frame) = read_limited_line(&mut reader)? {
        let line = match frame {
            Ok(line) => line,
            Err(()) => {
                write_line(&output, &error(None, -32700, "message too large"))?;
                continue;
            }
        };
        if line.is_empty() {
            continue;
        }
        if server.is_cancellation_line(&line) {
            server.handle_line(&line);
        } else if server.is_stop_line(&line) {
            if let Some(response) = server.handle_line(&line) {
                write_line(&output, &response)?;
            }
        } else if serde_json::from_str::<Value>(&line).ok().and_then(|value| {
            value
                .get("method")
                .and_then(Value::as_str)
                .map(str::to_owned)
        }) == Some("tools/call".into())
        {
            match sender.try_send(line) {
                Ok(()) => {}
                Err(TrySendError::Full(line)) => {
                    let id = serde_json::from_str::<Value>(&line)
                        .ok()
                        .and_then(|request| request.get("id").cloned());
                    write_line(&output, &error(id, -32000, "desktop action queue is full"))?;
                }
                Err(TrySendError::Disconnected(_line)) => break,
            }
        } else if let Some(response) = server.handle_line(&line) {
            write_line(&output, &response)?;
        }
    }
    drop(sender);
    let _ = worker.join();
    Ok(())
}
