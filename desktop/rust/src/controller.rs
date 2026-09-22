use crate::frames::{DisplayLayout, FrameStore};
use crate::{BackendError, DesktopBackend, protocol};
use base64::Engine;
use serde_json::{Value, json};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Clone, Default)]
pub struct CancellationHandle {
    active: Arc<Mutex<Option<ActiveCancellation>>>,
    next_generation: Arc<std::sync::atomic::AtomicU64>,
}

struct ActiveCancellation {
    request_id: Option<Value>,
    generation: u64,
    token: Arc<AtomicBool>,
}

impl CancellationHandle {
    pub fn cancel(&self) -> bool {
        let active = self.active.lock().expect("cancellation lock poisoned");
        if let Some(active) = active.as_ref() {
            active.token.store(true, Ordering::Release);
            true
        } else {
            false
        }
    }

    pub fn cancel_request(&self, request_id: &Value, generation: Option<u64>) -> bool {
        let active = self.active.lock().expect("cancellation lock poisoned");
        if let Some(active) = active.as_ref()
            && active.request_id.as_ref() == Some(request_id)
            && generation.is_none_or(|generation| generation == active.generation)
        {
            active.token.store(true, Ordering::Release);
            true
        } else {
            false
        }
    }

    fn is_cancelled(&self) -> bool {
        self.active
            .lock()
            .expect("cancellation lock poisoned")
            .as_ref()
            .is_some_and(|active| active.token.load(Ordering::Acquire))
    }

    fn begin(&self, request_id: Option<Value>) -> Arc<AtomicBool> {
        let token = Arc::new(AtomicBool::new(false));
        let generation = self.next_generation.fetch_add(1, Ordering::Relaxed) + 1;
        *self.active.lock().expect("cancellation lock poisoned") = Some(ActiveCancellation {
            request_id,
            generation,
            token: token.clone(),
        });
        token
    }

    fn finish(&self, token: &Arc<AtomicBool>) {
        let mut active = self.active.lock().expect("cancellation lock poisoned");
        if active
            .as_ref()
            .is_some_and(|current| Arc::ptr_eq(&current.token, token))
        {
            *active = None;
        }
    }
}

pub struct Controller<B> {
    backend: B,
    dry_run: bool,
    cancellation: CancellationHandle,
    frames: FrameStore,
    deadline: Option<Instant>,
}

impl<B: DesktopBackend> Controller<B> {
    pub fn new(backend: B, dry_run: bool) -> Self {
        Self {
            backend,
            dry_run,
            cancellation: CancellationHandle::default(),
            frames: FrameStore::new(64 * 1024 * 1024).expect("fixed frame budget is valid"),
            deadline: None,
        }
    }

    pub fn cancellation_handle(&self) -> CancellationHandle {
        self.cancellation.clone()
    }

    pub fn command(&mut self, name: &str, params: &Value) -> Value {
        self.command_with_request_id(name, params, None)
    }

    pub fn command_with_request_id(
        &mut self,
        name: &str,
        params: &Value,
        request_id: Option<Value>,
    ) -> Value {
        if let Err(error) = crate::validation::preflight(name, params) {
            return protocol::fail(error.code, &error.message, "fix the command and retry");
        }
        if let Some(error) = self.frame_preflight(name, params) {
            return error;
        }
        if let Some(error) = self.dynamic_preflight(name, params) {
            return error;
        }
        if name == "stop" {
            return protocol::ok(json!({"stopped": self.cancellation.cancel()}));
        }
        let token = self.cancellation.begin(request_id);
        let result = self.dispatch(name, params);
        self.cancellation.finish(&token);
        result
    }

    fn dispatch(&mut self, name: &str, params: &Value) -> Value {
        match name {
            "observe" => self.observe(params),
            "list_apps" => match self.backend.list_apps() {
                Ok(apps) => protocol::ok(json!({"apps": apps})),
                Err(error) => backend_error(error, self.backend.backend_name()),
            },
            "list_windows" => match self
                .backend
                .list_windows(params.get("app").and_then(Value::as_str).unwrap_or(""))
            {
                Ok(windows) => protocol::ok(json!({"windows": windows})),
                Err(error) => backend_error(error, self.backend.backend_name()),
            },
            "active-window" => match self.backend.active_window() {
                Ok(active_window) => protocol::ok(json!({"active_window": active_window})),
                Err(error) => backend_error(error, self.backend.backend_name()),
            },
            "focus_app" | "launch" => {
                let app = params["app"].as_str().unwrap_or("");
                if self.dry_run {
                    protocol::ok(json!({"app": app, "dry_run": true}))
                } else {
                    let result = if name == "launch" {
                        self.backend.launch(app)
                    } else {
                        self.backend.focus_app(app)
                    };
                    match result {
                        Ok(active_window) => protocol::ok(json!({
                            "executed": true,
                            "app": app,
                            "effect_verified": self.backend.app_matches(app, &active_window),
                            "active_window": active_window,
                        })),
                        Err(error) => backend_error(error, self.backend.backend_name()),
                    }
                }
            }
            "move" => self.pointer(name, params),
            "click" | "double-click" | "right_click" => self.pointer(name, params),
            "drag" | "scroll" => self.pointer(name, params),
            "type" | "click_type" | "press" | "hotkey" => self.keyboard(name, params),
            "wait" => {
                if self.dry_run {
                    protocol::ok(
                        json!({"seconds": params.get("seconds").cloned().unwrap_or(json!(1.0)), "dry_run": true}),
                    )
                } else {
                    let seconds = params.get("seconds").and_then(Value::as_f64).unwrap_or(1.0);
                    let deadline = Instant::now() + Duration::from_secs_f64(seconds);
                    while Instant::now() < deadline {
                        if let Some(error) = self.interruption_error() {
                            return error;
                        }
                        std::thread::sleep(
                            Duration::from_millis(10)
                                .min(deadline.saturating_duration_since(Instant::now())),
                        );
                    }
                    protocol::ok(json!({"executed": true, "seconds": seconds}))
                }
            }
            "batch" => self.batch(params),
            "stop" => protocol::ok(json!({"stopped": false})),
            "doctor" => self.doctor(),
            _ => unreachable!("validation rejects unknown commands"),
        }
    }

    fn dynamic_preflight(&self, name: &str, params: &Value) -> Option<Value> {
        if self.dry_run {
            return None;
        }
        if name == "batch" {
            let batch_app = params.get("app").and_then(Value::as_str).unwrap_or("");
            for (index, action) in params["actions"].as_array()?.iter().enumerate() {
                let operation = action["op"].as_str()?;
                let mut arguments = action.as_object()?.clone();
                arguments.remove("op");
                if (crate::validation::is_keyboard_command(operation) || operation == "batch")
                    && !arguments.contains_key("app")
                    && !batch_app.is_empty()
                {
                    arguments.insert("app".into(), Value::String(batch_app.into()));
                }
                if let Some(mut error) =
                    self.dynamic_preflight(operation, &Value::Object(arguments))
                {
                    if let Some(message) = error["error"]["message"].as_str() {
                        error["error"]["message"] =
                            Value::String(format!("action {index}: {message}"));
                    }
                    return Some(error);
                }
            }
            return None;
        }
        if !crate::validation::is_keyboard_command(name) {
            return None;
        }
        let position = (name == "click_type").then(|| {
            (
                params.get("x").and_then(Value::as_i64).unwrap_or(0),
                params.get("y").and_then(Value::as_i64).unwrap_or(0),
            )
        });
        self.keyboard_preflight(params, position).err()
    }

    fn keyboard_preflight(
        &self,
        params: &Value,
        position: Option<(i64, i64)>,
    ) -> Result<Value, Value> {
        let app = params.get("app").and_then(Value::as_str).unwrap_or("");
        let active = match self.backend.active_window() {
            Ok(active) => active,
            Err(error) => return Err(backend_error(error, self.backend.backend_name())),
        };
        if !self.backend.app_matches(app, &active) {
            return Err(protocol::fail(
                "focus_failed",
                &format!("refusing input: expected '{app}', frontmost is '{active}'"),
                "focus the target app and retry",
            ));
        }
        let state = match position {
            Some((x, y)) => self.backend.element_at(x, y),
            None => self.backend.focused_element(),
        };
        let state = match state {
            Ok(state) => state,
            Err(BackendError::Unsupported { .. }) => {
                return Err(protocol::fail(
                    "needs_attention",
                    "input safety state could not be inspected",
                    "inspect the target UI manually before retrying",
                ));
            }
            Err(BackendError::Failure(message) | BackendError::Focus(message)) => {
                return Err(protocol::fail(
                    "needs_attention",
                    &format!("input safety state could not be inspected: {message}"),
                    "inspect the target UI manually before retrying",
                ));
            }
            Err(error @ BackendError::Cancelled { .. }) => {
                return Err(backend_error(error, self.backend.backend_name()));
            }
        };
        if let Some(issue) = crate::safety::input_state_issue(&state) {
            return Err(protocol::fail(
                issue.code,
                issue.message,
                "inspect the target UI manually before retrying",
            ));
        }
        Ok(state)
    }

    fn frame_preflight(&self, name: &str, params: &Value) -> Option<Value> {
        if self.dry_run {
            return None;
        }
        if name == "batch" {
            for (index, action) in params["actions"].as_array()?.iter().enumerate() {
                let operation = action["op"].as_str()?;
                let mut arguments = action.as_object()?.clone();
                arguments.remove("op");
                if let Some(mut error) = self.frame_preflight(operation, &Value::Object(arguments))
                {
                    if let Some(message) = error["error"]["message"].as_str() {
                        error["error"]["message"] =
                            Value::String(format!("action {index}: {message}"));
                    }
                    return Some(error);
                }
            }
            return None;
        }
        if !crate::validation::is_coordinate_command(name) {
            return None;
        }
        let Some(frame_id) = params.get("frame_id").and_then(Value::as_str) else {
            return Some(protocol::fail(
                "stale_frame",
                "coordinates require a fresh frame_id",
                "call observe first, then pass its frame_id",
            ));
        };
        let layout = match self.backend.display_layout() {
            Ok(layout) => layout,
            Err(error) => return Some(backend_error(error, self.backend.backend_name())),
        };
        let layout: DisplayLayout = match serde_json::from_value(layout) {
            Ok(layout) => layout,
            Err(_) => {
                return Some(protocol::fail(
                    "exec_failed",
                    "backend returned invalid display layout",
                    "check doctor output",
                ));
            }
        };
        if let Err(message) = layout.validate() {
            return Some(protocol::fail(
                "exec_failed",
                &format!("backend returned invalid display layout: {message}"),
                "check doctor output",
            ));
        }
        let active_window = match self.backend.active_window() {
            Ok(active) => active,
            Err(error) => return Some(backend_error(error, self.backend.backend_name())),
        };
        let targets = if name == "drag" {
            vec![
                (
                    params.get("from_x").and_then(Value::as_i64).unwrap_or(0),
                    params.get("from_y").and_then(Value::as_i64).unwrap_or(0),
                ),
                (
                    params.get("to_x").and_then(Value::as_i64).unwrap_or(0),
                    params.get("to_y").and_then(Value::as_i64).unwrap_or(0),
                ),
            ]
        } else {
            vec![(
                params.get("x").and_then(Value::as_i64).unwrap_or(0),
                params.get("y").and_then(Value::as_i64).unwrap_or(0),
            )]
        };
        if !self
            .frames
            .authorizes(frame_id, &layout, &active_window, &targets)
        {
            return Some(protocol::fail(
                "stale_frame",
                &format!(
                    "frame {frame_id} is stale, geometry changed, or target is outside its region"
                ),
                "observe again and retry with the new frame_id",
            ));
        }
        None
    }

    fn pointer(&self, name: &str, params: &Value) -> Value {
        if !self.dry_run {
            return match name {
                "move" => {
                    let target = (params["x"].as_i64().unwrap(), params["y"].as_i64().unwrap());
                    match self.travel(params, target) {
                        Ok(()) => {
                            protocol::ok(json!({"executed": true, "x": target.0, "y": target.1}))
                        }
                        Err(error) => self.input_error("move", error),
                    }
                }
                "click" | "double-click" | "right_click" => {
                    let target = (params["x"].as_i64().unwrap(), params["y"].as_i64().unwrap());
                    if let Err(error) = self.travel(params, target) {
                        return self.input_error(name, error);
                    }
                    let button = if name == "right_click" {
                        "right"
                    } else {
                        "left"
                    };
                    let double = name == "double-click";
                    match self
                        .backend
                        .click(target.0, target.1, button, double, &|| self.interrupted())
                    {
                        Ok(()) => protocol::ok(json!({
                            "executed": true,
                            "x": target.0,
                            "y": target.1,
                            "button": button,
                            "double": double,
                        })),
                        Err(error) => self.input_error(name, error),
                    }
                }
                "drag" => {
                    let from = (
                        params["from_x"].as_i64().unwrap(),
                        params["from_y"].as_i64().unwrap(),
                    );
                    let to = (
                        params["to_x"].as_i64().unwrap(),
                        params["to_y"].as_i64().unwrap(),
                    );
                    if let Err(error) = self.travel(params, from) {
                        return self.input_error(name, error);
                    }
                    let seed = params.get("seed").and_then(Value::as_i64).unwrap_or(0);
                    let path = crate::motion::points(from, to, seed, 50);
                    match self.backend.drag(from, to, &path, &|| self.interrupted()) {
                        Ok(()) => protocol::ok(json!({"executed": true})),
                        Err(error) => self.input_error(name, error),
                    }
                }
                "scroll" => {
                    if let Err(error) = self.travel_to_current(params) {
                        return self.input_error(name, error);
                    }
                    let direction = params
                        .get("direction")
                        .and_then(Value::as_str)
                        .unwrap_or("down");
                    let amount = params.get("amount").and_then(Value::as_u64).unwrap_or(3) as usize;
                    match self
                        .backend
                        .scroll(direction, amount, &|| self.interrupted())
                    {
                        Ok(()) => protocol::ok(json!({
                            "executed": true,
                            "direction": direction,
                            "amount": amount,
                        })),
                        Err(error) => self.input_error(name, error),
                    }
                }
                _ => unreachable!("not a pointer command"),
            };
        }
        match name {
            "move" => {
                let target = (
                    params["x"].as_i64().unwrap_or(0),
                    params["y"].as_i64().unwrap_or(0),
                );
                let seed = params["seed"].as_i64().unwrap_or(0);
                let path = crate::motion::points((0, 0), target, seed, 50);
                protocol::ok(
                    json!({"x": target.0, "y": target.1, "points": path.len(), "dry_run": true}),
                )
            }
            "click" | "double-click" | "right_click" => protocol::ok(
                json!({"x": params["x"], "y": params["y"], "op": "click", "dry_run": true}),
            ),
            "drag" => protocol::ok(json!({"op": "drag", "dry_run": true})),
            "scroll" => protocol::ok(
                json!({"op": "scroll", "direction": params.get("direction").cloned().unwrap_or(json!("down")), "amount": params.get("amount").cloned().unwrap_or(json!(3)), "dry_run": true}),
            ),
            _ => unreachable!("not a pointer command"),
        }
    }

    fn travel(&self, params: &Value, target: (i64, i64)) -> Result<(), BackendError> {
        let start = self.backend.cursor_position()?;
        let seed = params.get("seed").and_then(Value::as_i64).unwrap_or(0);
        let path = crate::motion::points(start, target, seed, 50);
        let distance = std::iter::once(start)
            .chain(path.iter().copied())
            .collect::<Vec<_>>()
            .windows(2)
            .map(|pair| ((pair[1].0 - pair[0].0) as f64).hypot((pair[1].1 - pair[0].1) as f64))
            .sum::<f64>();
        let duration = crate::motion::movement_time(distance, 1.0).max(0.0);
        self.backend
            .move_path(&path, duration, &|| self.interrupted())?;
        if self.interrupted() {
            return Err(BackendError::Cancelled {
                operation: "move".into(),
                completed: path.len(),
                total: path.len(),
            });
        }
        Ok(())
    }

    fn travel_to_current(&self, params: &Value) -> Result<(), BackendError> {
        let current = self.backend.cursor_position()?;
        self.travel(params, current)
    }

    fn input_error(&self, operation: &str, error: BackendError) -> Value {
        match error {
            BackendError::Failure(_) => {
                let _ = self.backend.release_all();
                protocol::partial(
                    json!({
                        "executed": false,
                        "last_completed": Value::Null,
                        "receipts": [{"step": operation, "status": "unknown"}],
                    }),
                    "exec_failed",
                    &format!(
                        "{operation} failed after input dispatch began; completion is unknown"
                    ),
                    "inspect the target before retrying; input cannot be undone",
                )
            }
            BackendError::Cancelled {
                operation,
                completed,
                total,
            } if self.deadline_expired() => deadline_error(&operation, completed, total),
            other => backend_error(other, self.backend.backend_name()),
        }
    }

    fn doctor(&self) -> Value {
        let mut checks = serde_json::Map::new();
        checks.insert(
            "helper".into(),
            doctor_check(
                self.backend.helper_available(),
                "reinstall the package or build native/cghelper.c with ./install",
            ),
        );
        checks.insert(
            "accessibility".into(),
            doctor_check(
                self.backend.accessibility_trusted(),
                "grant Accessibility permission to the installed controller, then retry",
            ),
        );
        checks.insert(
            "screen_recording".into(),
            doctor_check(
                self.backend.screen_recording_authorized(),
                "grant Screen Recording permission to the installed controller, then retry",
            ),
        );
        let mut capture = doctor_check(
            self.backend.capture_available(),
            "install a build with native screenshot capture support",
        );
        if capture["ok"] == true {
            capture["message"] =
                Value::String("available (native Rust capture; MSS is not required)".into());
        }
        checks.insert("mss".into(), capture);
        let ready = checks.values().all(|check| check["ok"] == true);
        protocol::ok(json!({
            "platform": self.backend.backend_name(),
            "version": env!("CARGO_PKG_VERSION"),
            "ready": ready,
            "checks": checks,
        }))
    }

    fn keyboard(&self, name: &str, params: &Value) -> Value {
        if !self.dry_run {
            return self.live_keyboard(name, params);
        }
        if name == "type" {
            let text = params["text"].as_str().unwrap_or("");
            protocol::ok(json!({"typed": text.chars().count(), "dry_run": true}))
        } else if name == "click_type" {
            let text = params["text"].as_str().unwrap_or("");
            protocol::ok(
                json!({"typed": text.chars().count(), "x": params["x"], "y": params["y"], "app": params["app"], "dry_run": true}),
            )
        } else {
            let keys = crate::validation::canonical_keys(params["keys"].as_str().unwrap_or(""));
            protocol::ok(json!({"keys": keys, "dry_run": true}))
        }
    }

    fn live_keyboard(&self, name: &str, params: &Value) -> Value {
        let text = params.get("text").and_then(Value::as_str).unwrap_or("");
        let target = (
            params["x"].as_i64().unwrap_or(0),
            params["y"].as_i64().unwrap_or(0),
        );
        let travel = if name == "click_type" {
            self.travel(params, target)
        } else {
            self.travel_to_current(params)
        };
        if let Err(error) = travel {
            return self.input_error(name, error);
        }

        let clicked = if name == "click_type" {
            if let Err(error) = self
                .backend
                .click(target.0, target.1, "left", false, &|| self.interrupted())
            {
                return self.input_error("click", error);
            }
            true
        } else {
            false
        };

        let before_state = match self.keyboard_preflight(params, None) {
            Ok(state) => state,
            Err(error) if clicked => {
                return protocol::partial(
                    json!({
                        "executed": false,
                        "clicked": true,
                        "typed": false,
                        "last_completed": "click",
                        "receipts": [{"step": "click", "status": "ok"}],
                    }),
                    error["error"]["code"].as_str().unwrap_or("needs_attention"),
                    error["error"]["message"]
                        .as_str()
                        .unwrap_or("input safety check failed"),
                    error["error"]["recover"].as_str().unwrap_or(""),
                );
            }
            Err(error) => return error,
        };

        if matches!(name, "type" | "click_type") {
            let mode = params
                .get("timing")
                .and_then(Value::as_str)
                .unwrap_or("native");
            let gaps = crate::timing::gaps_for(mode, text).expect("timing was validated");
            return match self.backend.type_text(text, &gaps, &|| self.interrupted()) {
                Ok(count) if count == text.chars().count() => {
                    let mut result = protocol::ok(json!({"executed": true, "chars": count}));
                    self.attach_effect_verification(
                        &mut result,
                        params,
                        name,
                        text,
                        Some(&before_state),
                    );
                    result
                }
                Ok(count) if count < text.chars().count() => {
                    let mut data = json!({
                        "executed": false,
                        "typed": false,
                        "chars": count,
                        "requested_chars": text.chars().count(),
                        "last_completed": if clicked { json!("click") } else { json!(count as i64 - 1) },
                        "receipts": if clicked {
                            json!([
                                {"step": "click", "status": "ok"},
                                {"step": "type", "status": "partial", "completed_chars": count}
                            ])
                        } else {
                            json!([{"step": "type", "status": "partial", "completed_chars": count}])
                        },
                    });
                    if clicked {
                        data["clicked"] = Value::Bool(true);
                    }
                    protocol::partial(
                        data,
                        "exec_failed",
                        &format!(
                            "backend typed {count} of {} characters{}",
                            text.chars().count(),
                            if clicked { " after clicking" } else { "" }
                        ),
                        if clicked {
                            "inspect the target before retrying; executed input cannot be undone"
                        } else {
                            "inspect the target before retrying; typed input cannot be undone"
                        },
                    )
                }
                Ok(_) => self.typing_error(
                    text.chars().count(),
                    clicked,
                    BackendError::Failure(
                        "backend returned an invalid typed-character count".into(),
                    ),
                ),
                Err(error) => self.typing_error(text.chars().count(), clicked, error),
            };
        }

        let keys = crate::validation::canonical_keys(params["keys"].as_str().unwrap_or(""));
        match self.backend.key(&keys, &|| self.interrupted()) {
            Ok(()) => {
                let mut result = protocol::ok(json!({"executed": true, "keys": keys}));
                self.attach_effect_verification(&mut result, params, name, "", Some(&before_state));
                result
            }
            Err(error) => self.input_error(name, error),
        }
    }

    fn attach_effect_verification(
        &self,
        result: &mut Value,
        params: &Value,
        operation: &str,
        text: &str,
        before_state: Option<&Value>,
    ) {
        let Some(mode) = params.get("verify").and_then(Value::as_str) else {
            return;
        };
        let verified = if mode == "focus" {
            let app = params.get("app").and_then(Value::as_str).unwrap_or("");
            self.backend
                .active_window()
                .ok()
                .map(|active| self.backend.app_matches(app, &active))
        } else if matches!(operation, "type" | "click_type") {
            let before = before_state
                .and_then(|state| state.get("value"))
                .and_then(Value::as_str);
            let after = self.backend.focused_element().ok().and_then(|state| {
                state
                    .get("value")
                    .and_then(Value::as_str)
                    .map(str::to_owned)
            });
            before
                .zip(after.as_deref())
                .map(|(before, after)| proves_text_insertion(before, after, text))
        } else {
            None
        };
        result["data"]["effect_verified"] = verified.map_or(Value::Null, Value::Bool);
    }

    fn typing_error(&self, requested: usize, clicked: bool, error: BackendError) -> Value {
        match error {
            BackendError::Failure(_) => {
                let _ = self.backend.release_all();
                let receipts = if clicked {
                    json!([
                        {"step": "click", "status": "ok"},
                        {"step": "type", "status": "unknown"}
                    ])
                } else {
                    json!([{"step": "type", "status": "unknown"}])
                };
                let mut data = json!({
                    "executed": false,
                    "typed": false,
                    "chars": Value::Null,
                    "requested_chars": requested,
                    "last_completed": if clicked { json!("click") } else { Value::Null },
                    "receipts": receipts,
                });
                if clicked {
                    data["clicked"] = Value::Bool(true);
                }
                protocol::partial(
                    data,
                    "exec_failed",
                    "typing failed after input dispatch began; completion is unknown",
                    "inspect the target before retrying; typed input cannot be undone",
                )
            }
            BackendError::Cancelled {
                operation,
                completed,
                total,
            } if self.deadline_expired() => deadline_error(&operation, completed, total),
            other => backend_error(other, self.backend.backend_name()),
        }
    }

    fn deadline_expired(&self) -> bool {
        self.deadline
            .is_some_and(|deadline| Instant::now() >= deadline)
    }

    fn interrupted(&self) -> bool {
        self.cancellation.is_cancelled() || self.deadline_expired()
    }

    fn interruption_error(&self) -> Option<Value> {
        if self.deadline_expired() {
            Some(protocol::fail(
                "deadline_exceeded",
                "batch deadline exceeded",
                "inspect partial progress before issuing a new request",
            ))
        } else if self.cancellation.is_cancelled() {
            Some(protocol::fail(
                "cancelled",
                "operation cancelled by stop",
                "issue a new request; cancellation is request-scoped",
            ))
        } else {
            None
        }
    }

    fn batch(&mut self, params: &Value) -> Value {
        let actions = params["actions"]
            .as_array()
            .expect("batch preflight checked actions");
        let mut receipts = Vec::with_capacity(actions.len());
        let mut last_completed: i64 = -1;
        let previous_deadline = self.deadline;
        if let Some(milliseconds) = params.get("deadline_ms").and_then(Value::as_f64) {
            let own = Instant::now() + Duration::from_secs_f64(milliseconds / 1000.0);
            self.deadline = Some(previous_deadline.map_or(own, |parent| parent.min(own)));
        }
        let mut result = 'actions: {
            for (index, action) in actions.iter().enumerate() {
                if let Some(error) = self.interruption_error() {
                    let code = error["error"]["code"].as_str().unwrap_or("cancelled");
                    break 'actions protocol::partial(
                        json!({"status": code, "last_completed": last_completed, "receipts": receipts}),
                        code,
                        &format!("batch {code} at action {}", last_completed + 1),
                        "inspect receipts; executed events cannot be undone",
                    );
                }
                let mut arguments = action
                    .as_object()
                    .expect("batch preflight checked action")
                    .clone();
                let operation = arguments
                    .remove("op")
                    .and_then(|value| value.as_str().map(str::to_owned))
                    .expect("batch preflight checked op");
                let keyboard = crate::validation::is_keyboard_command(&operation);
                let input = crate::validation::is_input_command(&operation);
                for field in ["risk", "confirm"] {
                    if (input || operation == "batch")
                        && !arguments.contains_key(field)
                        && let Some(value) = params.get(field)
                    {
                        arguments.insert(field.to_owned(), value.clone());
                    }
                }
                if (keyboard || operation == "batch")
                    && !arguments.contains_key("app")
                    && let Some(value) = params.get("app")
                {
                    arguments.insert("app".to_owned(), value.clone());
                }
                let arguments = Value::Object(arguments);
                let result = self
                    .frame_preflight(&operation, &arguments)
                    .or_else(|| self.dynamic_preflight(&operation, &arguments))
                    .unwrap_or_else(|| self.dispatch(&operation, &arguments));
                if result["ok"] == true {
                    last_completed = index as i64;
                    receipts.push(json!({"index": index, "status": "ok", "data": result["data"]}));
                } else {
                    let mut receipt =
                        json!({"index": index, "status": "failed", "error": result["error"]});
                    if let Some(data) = result.get("data") {
                        receipt["data"] = data.clone();
                    }
                    receipts.push(receipt);
                    let code = result["error"]["code"].as_str().unwrap_or("exec_failed");
                    let status = if matches!(code, "cancelled" | "deadline_exceeded") {
                        code
                    } else {
                        "failed"
                    };
                    break 'actions protocol::partial(
                        json!({"status": status, "last_completed": last_completed, "receipts": receipts}),
                        code,
                        &format!("batch {status} at action {}", last_completed + 1),
                        "inspect receipts; executed events cannot be undone",
                    );
                }
            }
            protocol::ok(
                json!({"status": "completed", "last_completed": last_completed, "receipts": receipts}),
            )
        };
        self.deadline = previous_deadline;
        if let Some(final_observe) = params.get("final_observe") {
            let observation = self.observe(&if final_observe["image"] == true {
                json!({})
            } else {
                json!({"metadata_only": true})
            });
            let descriptor = if observation["ok"] == true {
                let mut observation_data = observation["data"].clone();
                let image = observation_data
                    .as_object_mut()
                    .and_then(|data| data.remove("image_b64"));
                if let Some(image) = image
                    && let Some(data) = result.get_mut("data").and_then(Value::as_object_mut)
                {
                    data.insert("image_b64".into(), image);
                }
                json!({"ok": true, "data": observation_data})
            } else {
                json!({"ok": false, "error": observation["error"]})
            };
            if let Some(data) = result.get_mut("data").and_then(Value::as_object_mut) {
                data.insert("final_observation".into(), descriptor);
            }
        }
        result
    }

    fn observe(&mut self, params: &Value) -> Value {
        let layout = match self.backend.display_layout() {
            Ok(layout) => layout,
            Err(error) => return backend_error(error, self.backend.backend_name()),
        };
        let Some((left, top, width, height)) = layout_bounds(&layout) else {
            return protocol::fail(
                "exec_failed",
                "backend returned invalid display layout",
                "check doctor output",
            );
        };
        let region = match params.get("region") {
            None | Some(Value::Null) => Some((left, top, width, height)),
            Some(Value::String(s)) if s.trim().is_empty() => Some((left, top, width, height)),
            Some(Value::String(s)) => match parse_region(s) {
                Ok(region) => Some(region),
                Err(message) => {
                    return protocol::fail("bad_arg", message, "pass region as x,y,w,h");
                }
            },
            Some(_) => {
                return protocol::fail(
                    "bad_arg",
                    "region must be a string",
                    "pass region as x,y,w,h",
                );
            }
        };
        let Some((x, y, w, h)) = region else {
            unreachable!()
        };
        if x < left
            || y < top
            || x.saturating_add(w) > left.saturating_add(width)
            || y.saturating_add(h) > top.saturating_add(height)
        {
            return protocol::fail(
                "bad_arg",
                "capture region is outside the current display layout",
                "choose a region inside the reported layout bounds",
            );
        }
        if !self.dry_run {
            let typed_layout: DisplayLayout = match serde_json::from_value(layout.clone()) {
                Ok(layout) => layout,
                Err(_) => {
                    return protocol::fail(
                        "exec_failed",
                        "backend returned invalid display layout",
                        "check doctor output",
                    );
                }
            };
            if let Err(message) = typed_layout.validate() {
                return protocol::fail(
                    "exec_failed",
                    &format!("backend returned invalid display layout: {message}"),
                    "check doctor output",
                );
            }
            let path_mode = params["path_mode"] == true;
            let include_image = params["metadata_only"] != true && !path_mode;
            if let Err(message) = self.frames.preflight_capture(w, h, include_image) {
                return protocol::fail("exec_failed", &message, "capture a smaller region");
            }
            let active_window = match self.backend.active_window() {
                Ok(name) => name,
                Err(error) => return backend_error(error, self.backend.backend_name()),
            };
            let image = match self.backend.capture_png(x, y, w, h) {
                Ok(image) => image,
                Err(error) => return backend_error(error, self.backend.backend_name()),
            };
            let active_window_after = match self.backend.active_window() {
                Ok(name) => name,
                Err(error) => return backend_error(error, self.backend.backend_name()),
            };
            if active_window_after != active_window {
                self.frames.clear();
                return protocol::fail(
                    "stale_frame",
                    "foreground application changed during screen capture",
                    "observe again after focus settles",
                );
            }
            if !image.starts_with(b"\x89PNG\r\n\x1a\n") {
                self.frames.clear();
                return protocol::fail(
                    "exec_failed",
                    "backend returned invalid PNG screenshot data",
                    "check doctor output",
                );
            }
            let stored = if path_mode {
                self.frames
                    .insert_path(typed_layout, (x, y, w, h), active_window.clone(), &image)
            } else {
                self.frames.insert(
                    typed_layout,
                    (x, y, w, h),
                    active_window.clone(),
                    include_image.then_some(image),
                )
            };
            let frame = match stored {
                Ok(frame) => frame,
                Err(message) => {
                    return protocol::fail("exec_failed", &message, "capture a smaller region");
                }
            };
            let mut data = json!({
                "frame_id": frame.id,
                "region": [x, y, w, h],
                "screen": {"width": width, "height": height, "origin": [left, top]},
                "layout": layout,
                "active_window": active_window,
            });
            if let Some(image) = frame.image() {
                data["image_b64"] =
                    Value::String(base64::engine::general_purpose::STANDARD.encode(image));
            }
            if let Some(path) = frame.path() {
                data["path"] = Value::String(path.to_string_lossy().into_owned());
            }
            return protocol::ok(data);
        }
        protocol::ok(json!({"region": [x, y, w, h], "layout": layout, "dry_run": true}))
    }
}

fn backend_error(error: BackendError, backend_name: &str) -> Value {
    match error {
        BackendError::Unsupported {
            capability,
            message,
        } => protocol::fail(
            "unsupported",
            &message,
            &format!("'{capability}' is unavailable on {backend_name}"),
        ),
        BackendError::Failure(message) => protocol::fail(
            "exec_failed",
            &message,
            "grant OS permissions or check doctor output",
        ),
        BackendError::Focus(message) => protocol::fail(
            "focus_failed",
            &message,
            "focus the target app and retry; check active-window",
        ),
        BackendError::Cancelled {
            operation,
            completed,
            total,
        } => protocol::partial(
            json!({
                "operation": operation,
                "completed_primitives": completed,
                "total_primitives": total,
            }),
            "cancelled",
            "operation cancelled by stop",
            "inspect partial progress before issuing a new request",
        ),
    }
}

fn deadline_error(operation: &str, completed: usize, total: usize) -> Value {
    protocol::partial(
        json!({
            "operation": operation,
            "completed_primitives": completed,
            "total_primitives": total,
        }),
        "deadline_exceeded",
        "batch deadline exceeded",
        "inspect partial progress before issuing a new request",
    )
}

fn proves_text_insertion(before: &str, after: &str, text: &str) -> bool {
    if after.chars().count() != before.chars().count() + text.chars().count() {
        return false;
    }
    before
        .char_indices()
        .map(|(index, _)| index)
        .chain(std::iter::once(before.len()))
        .any(|index| {
            after
                .strip_prefix(&before[..index])
                .is_some_and(|rest| rest.strip_prefix(text) == Some(&before[index..]))
        })
}

fn doctor_check(result: Result<bool, BackendError>, recover: &str) -> Value {
    match result {
        Ok(ok) => json!({
            "ok": ok,
            "message": if ok { "available" } else { "missing or not authorized" },
            "recover": recover,
        }),
        Err(BackendError::Unsupported {
            capability,
            message,
        }) => json!({
            "ok": Value::Null,
            "message": message,
            "recover": if capability == "helper" {
                format!("restore the native helper with ./install, then {recover}")
            } else {
                recover.to_owned()
            },
        }),
        Err(BackendError::Failure(message)) => json!({
            "ok": Value::Null,
            "message": message,
            "recover": recover,
        }),
        Err(BackendError::Focus(message)) => json!({
            "ok": Value::Null,
            "message": message,
            "recover": recover,
        }),
        Err(BackendError::Cancelled { .. }) => json!({
            "ok": Value::Null,
            "message": "diagnostic probe was cancelled",
            "recover": recover,
        }),
    }
}

fn parse_region(value: &str) -> Result<(i64, i64, i64, i64), &'static str> {
    if value.trim().is_empty() {
        return Err("region must be x,y,w,h integers");
    }
    let parts: Vec<_> = value.split(',').map(str::trim).collect();
    if parts.len() != 4 {
        return Err("region must be x,y,w,h integers");
    }
    let parsed: Result<Vec<i64>, _> = parts.iter().map(|part| part.parse()).collect();
    let values = parsed.map_err(|_| "region must be x,y,w,h integers")?;
    if values[2] <= 0 || values[3] <= 0 {
        return Err("region width/height must be positive");
    }
    Ok((values[0], values[1], values[2], values[3]))
}

fn layout_bounds(layout: &Value) -> Option<(i64, i64, i64, i64)> {
    let origin = layout.get("origin")?.as_array()?;
    if origin.len() != 2 {
        return None;
    }
    let x = origin[0].as_i64()?;
    let y = origin[1].as_i64()?;
    let width = layout.get("width")?.as_i64()?;
    let height = layout.get("height")?.as_i64()?;
    (width > 0 && height > 0).then_some((x, y, width, height))
}
