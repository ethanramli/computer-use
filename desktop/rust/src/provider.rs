use serde_json::{Value, json};

#[cfg(target_os = "macos")]
use std::io::{Read, Write};
#[cfg(target_os = "macos")]
use std::path::PathBuf;
#[cfg(target_os = "macos")]
use std::process::{Command, Stdio};

#[derive(Debug)]
pub enum BackendError {
    Unsupported {
        capability: &'static str,
        message: String,
    },
    Focus(String),
    Cancelled {
        operation: String,
        completed: usize,
        total: usize,
    },
    Failure(String),
}

pub type BackendResult<T> = Result<T, BackendError>;

const MOCK_PNG: &[u8] = &[
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x04, 0x00, 0x00, 0x00, 0xb5, 0x1c, 0x0c,
    0x02, 0x00, 0x00, 0x00, 0x0b, 0x49, 0x44, 0x41, 0x54, 0x78, 0xda, 0x63, 0x64, 0xf8, 0x0f, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x27, 0x18, 0xe3, 0x66, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44,
    0xae, 0x42, 0x60, 0x82,
];

#[cfg(target_os = "macos")]
const FRONTMOST_APP_SCRIPT: &str = concat!(
    "ObjC.import(\"AppKit\"); ",
    "const app = $.NSWorkspace.sharedWorkspace.frontmostApplication; ",
    "app ? ObjC.unwrap(app.localizedName) : \"\""
);

#[cfg(target_os = "macos")]
const RUNNING_APPS_SCRIPT: &str = concat!(
    "ObjC.import(\"AppKit\"); ",
    "const apps = $.NSWorkspace.sharedWorkspace.runningApplications; ",
    "const names = []; ",
    "for (let i = 0; i < apps.count; i++) { ",
    "const app = apps.objectAtIndex(i); ",
    "if (app.activationPolicy === $.NSApplicationActivationPolicyRegular) { ",
    "const n = ObjC.unwrap(app.localizedName); if (n) names.push(n); } } ",
    "JSON.stringify(names);"
);

/// Platform seam used by the shared command controller.
pub trait DesktopBackend {
    fn display_layout(&self) -> BackendResult<Value>;
    fn active_window(&self) -> BackendResult<String>;
    fn capture_png(&self, _x: i64, _y: i64, _width: i64, _height: i64) -> BackendResult<Vec<u8>> {
        Err(BackendError::Unsupported {
            capability: "screen_capture",
            message: "screen capture is not supported by this backend".into(),
        })
    }

    fn app_matches(&self, requested: &str, actual: &str) -> bool {
        requested.trim().eq_ignore_ascii_case(actual.trim())
    }

    fn focus_app(&self, _app: &str) -> BackendResult<String> {
        Err(BackendError::Unsupported {
            capability: "focus_app",
            message: "application focus is not supported by this backend".into(),
        })
    }

    fn launch(&self, _app: &str) -> BackendResult<String> {
        Err(BackendError::Unsupported {
            capability: "launch",
            message: "application launch is not supported by this backend".into(),
        })
    }

    fn focused_element(&self) -> BackendResult<Value> {
        Err(BackendError::Unsupported {
            capability: "focused_element",
            message: "focused element lookup is not supported by this backend".into(),
        })
    }

    fn element_at(&self, _x: i64, _y: i64) -> BackendResult<Value> {
        Err(BackendError::Unsupported {
            capability: "element_at",
            message: "coordinate element lookup is not supported by this backend".into(),
        })
    }

    fn cursor_position(&self) -> BackendResult<(i64, i64)> {
        Err(BackendError::Unsupported {
            capability: "cursor_position",
            message: "cursor position is not supported by this backend".into(),
        })
    }

    fn move_path(
        &self,
        _points: &[(i64, i64)],
        _total_secs: f64,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        Err(BackendError::Unsupported {
            capability: "pointer_input",
            message: "pointer movement is not supported by this backend".into(),
        })
    }

    fn click(
        &self,
        _x: i64,
        _y: i64,
        _button: &str,
        _double: bool,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        Err(BackendError::Unsupported {
            capability: "pointer_input",
            message: "click input is not supported by this backend".into(),
        })
    }

    fn drag(
        &self,
        _from: (i64, i64),
        _to: (i64, i64),
        _path: &[(i64, i64)],
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        Err(BackendError::Unsupported {
            capability: "pointer_input",
            message: "drag input is not supported by this backend".into(),
        })
    }

    fn scroll(
        &self,
        _direction: &str,
        _amount: usize,
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        Err(BackendError::Unsupported {
            capability: "pointer_input",
            message: "scroll input is not supported by this backend".into(),
        })
    }

    fn type_text(
        &self,
        _text: &str,
        _gaps: &[f64],
        _cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<usize> {
        Err(BackendError::Unsupported {
            capability: "keyboard_input",
            message: "text input is not supported by this backend".into(),
        })
    }

    fn key(&self, _keys: &str, _cancelled: &dyn Fn() -> bool) -> BackendResult<()> {
        Err(BackendError::Unsupported {
            capability: "keyboard_input",
            message: "key input is not supported by this backend".into(),
        })
    }

    fn release_all(&self) -> BackendResult<()> {
        Ok(())
    }
    fn backend_name(&self) -> &'static str {
        "unknown"
    }

    fn helper_available(&self) -> BackendResult<bool> {
        Err(BackendError::Unsupported {
            capability: "helper",
            message: "native helper status is unavailable".into(),
        })
    }

    fn accessibility_trusted(&self) -> BackendResult<bool> {
        Err(BackendError::Unsupported {
            capability: "accessibility",
            message: "Accessibility status is unavailable".into(),
        })
    }

    fn screen_recording_authorized(&self) -> BackendResult<bool> {
        Err(BackendError::Unsupported {
            capability: "screen_recording",
            message: "Screen Recording status is unavailable".into(),
        })
    }

    fn capture_available(&self) -> BackendResult<bool> {
        Err(BackendError::Unsupported {
            capability: "screen_capture",
            message: "screen capture runtime is unavailable".into(),
        })
    }

    fn list_apps(&self) -> BackendResult<Vec<String>> {
        Err(BackendError::Unsupported {
            capability: "list_apps",
            message: "list_apps is not supported by this backend".into(),
        })
    }

    fn list_windows(&self, _app: &str) -> BackendResult<Vec<Value>> {
        Err(BackendError::Unsupported {
            capability: "list_windows",
            message: "list_windows is not supported by this backend".into(),
        })
    }
}

/// Repeatable provider for contract tests; it never accesses the real desktop.
#[derive(Default)]
pub struct MockBackend;

impl DesktopBackend for MockBackend {
    fn display_layout(&self) -> BackendResult<Value> {
        Ok(json!({
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
        }))
    }

    fn active_window(&self) -> BackendResult<String> {
        Ok("Finder".to_owned())
    }

    fn capture_png(&self, _x: i64, _y: i64, _width: i64, _height: i64) -> BackendResult<Vec<u8>> {
        Ok(MOCK_PNG.to_vec())
    }

    fn backend_name(&self) -> &'static str {
        "fake"
    }

    fn helper_available(&self) -> BackendResult<bool> {
        Ok(true)
    }

    fn accessibility_trusted(&self) -> BackendResult<bool> {
        Ok(true)
    }

    fn screen_recording_authorized(&self) -> BackendResult<bool> {
        Ok(true)
    }

    fn capture_available(&self) -> BackendResult<bool> {
        Ok(true)
    }

    fn list_apps(&self) -> BackendResult<Vec<String>> {
        Err(BackendError::Unsupported {
            capability: "list_apps",
            message: "not supported by this backend".into(),
        })
    }

    fn list_windows(&self, _app: &str) -> BackendResult<Vec<Value>> {
        Err(BackendError::Unsupported {
            capability: "list_windows",
            message: "not supported by this backend".into(),
        })
    }
}

/// Production CLI fallback until an OS provider is qualified for this build.
pub struct UnavailableBackend;

impl UnavailableBackend {
    pub fn current() -> Self {
        Self
    }
}

impl DesktopBackend for UnavailableBackend {
    fn display_layout(&self) -> BackendResult<Value> {
        Err(BackendError::Unsupported {
            capability: "display_layout",
            message: "display geometry is unavailable on this build".into(),
        })
    }

    fn active_window(&self) -> BackendResult<String> {
        Err(BackendError::Unsupported {
            capability: "active_window",
            message: "active-window inspection is unavailable on this build".into(),
        })
    }

    fn backend_name(&self) -> &'static str {
        "unavailable"
    }
}

/// Native macOS adapter over the existing helper and read-only AppKit/JXA calls.
#[cfg(target_os = "macos")]
pub struct MacOsBackend {
    helper: PathBuf,
    osascript: PathBuf,
    open: PathBuf,
}

#[cfg(target_os = "macos")]
impl MacOsBackend {
    pub fn new() -> Self {
        let helper = std::env::current_exe()
            .ok()
            .and_then(|path| path.parent().map(|parent| parent.join("cghelper")))
            .filter(|path| path.is_file())
            .unwrap_or_else(|| {
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../build/cghelper")
            });
        Self {
            helper,
            osascript: PathBuf::from("/usr/bin/osascript"),
            open: PathBuf::from("/usr/bin/open"),
        }
    }

    pub fn current() -> Self {
        Self::new()
    }

    #[cfg(test)]
    fn with_tools(helper: PathBuf, osascript: PathBuf) -> Self {
        Self {
            helper,
            osascript,
            open: PathBuf::from("/usr/bin/open"),
        }
    }

    fn helper_bytes(
        &self,
        arguments: &[String],
        capability: &'static str,
    ) -> BackendResult<Vec<u8>> {
        if !self.helper.is_file() {
            return Err(BackendError::Unsupported {
                capability: "helper",
                message: "cghelper missing: run ./install or place cghelper beside the Rust binary"
                    .into(),
            });
        }
        let mut command = Command::new(&self.helper);
        command.args(arguments);
        let output = output_with_timeout(&mut command, std::time::Duration::from_secs(120))
            .map_err(BackendError::Failure)?;
        if !output.status.success() {
            let message = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            let capability = if message.contains("Screen Recording") {
                "screen_recording"
            } else {
                capability
            };
            return Err(BackendError::Unsupported {
                capability,
                message: if message.is_empty() {
                    format!("native helper exited with {}", output.status)
                } else {
                    message
                },
            });
        }
        Ok(output.stdout)
    }

    fn helper(&self, argument: &str, capability: &'static str) -> BackendResult<String> {
        let output = self.helper_bytes(&[argument.into()], capability)?;
        Ok(String::from_utf8_lossy(&output).trim().to_owned())
    }

    fn helper_json(&self, arguments: &[String], capability: &'static str) -> BackendResult<Value> {
        let output = self.helper_bytes(arguments, capability)?;
        let state: Value =
            serde_json::from_slice(&output).map_err(|_| BackendError::Unsupported {
                capability,
                message: "cghelper returned invalid accessibility metadata".into(),
            })?;
        if !state.is_object() {
            return Err(BackendError::Unsupported {
                capability,
                message: "cghelper returned invalid accessibility metadata".into(),
            });
        }
        Ok(state)
    }

    fn jxa(&self, script: &str) -> Result<String, String> {
        command_output(Command::new(&self.osascript).args(["-l", "JavaScript", "-e", script]))
    }

    fn activate(&self, app: &str) -> Result<(), String> {
        const SCRIPT: &str = "function run(argv) { Application(argv[0]).activate(); }";
        if command_output(Command::new(&self.osascript).args([
            "-l",
            "JavaScript",
            "-e",
            SCRIPT,
            app,
        ]))
        .is_ok()
        {
            return Ok(());
        }
        command_output(Command::new(&self.open).args(["-a", app])).map(|_| ())?;
        command_output(Command::new(&self.osascript).args(["-l", "JavaScript", "-e", SCRIPT, app]))
            .map(|_| ())
    }

    fn input(
        &self,
        arguments: &[String],
        stdin: Option<&[u8]>,
        operation: &str,
        total: usize,
        cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<usize> {
        if cancelled() {
            return Err(BackendError::Cancelled {
                operation: operation.into(),
                completed: 0,
                total,
            });
        }
        if !self.helper.is_file() {
            return Err(BackendError::Unsupported {
                capability: "helper",
                message: "cghelper missing: run ./install or place cghelper beside the Rust binary"
                    .into(),
            });
        }
        let mut command = Command::new(&self.helper);
        command
            .args(arguments)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if stdin.is_some() {
            command.stdin(Stdio::piped());
        }
        let mut child = command
            .spawn()
            .map_err(|error| BackendError::Failure(error.to_string()))?;
        if let Some(bytes) = stdin
            && let Some(mut input) = child.stdin.take()
            && let Err(error) = input.write_all(bytes)
        {
            let _ = child.kill();
            return Err(BackendError::Failure(error.to_string()));
        }
        let mut was_cancelled = false;
        let started = std::time::Instant::now();
        let mut stop_deadline = None;
        loop {
            if cancelled() && !was_cancelled {
                was_cancelled = true;
                let _ = Command::new("/bin/kill")
                    .args(["-TERM", &child.id().to_string()])
                    .status();
                stop_deadline = Some(std::time::Instant::now() + std::time::Duration::from_secs(1));
            }
            if stop_deadline.is_some_and(|deadline| std::time::Instant::now() >= deadline) {
                let _ = child.kill();
            }
            if started.elapsed() >= std::time::Duration::from_secs(120) {
                let _ = child.kill();
                let _ = child.wait();
                return Err(BackendError::Failure(
                    "cghelper timed out after 120 seconds".into(),
                ));
            }
            match child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) => {
                    std::thread::sleep(std::time::Duration::from_millis(10));
                }
                Err(error) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(BackendError::Failure(error.to_string()));
                }
            }
        }
        let output = child
            .wait_with_output()
            .map_err(|error| BackendError::Failure(error.to_string()))?;
        let completed = String::from_utf8_lossy(&output.stdout)
            .lines()
            .next_back()
            .and_then(|line| line.trim().parse::<usize>().ok())
            .unwrap_or(0);
        if was_cancelled || output.status.code() == Some(130) {
            return Err(BackendError::Cancelled {
                operation: operation.into(),
                completed,
                total,
            });
        }
        if output.status.code() == Some(5) {
            return Err(BackendError::Unsupported {
                capability: "accessibility",
                message: String::from_utf8_lossy(&output.stderr).trim().to_owned(),
            });
        }
        if !output.status.success() {
            let message = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            return Err(BackendError::Failure(if message.is_empty() {
                format!("cghelper exited with {}", output.status)
            } else {
                message
            }));
        }
        if total > 0 && completed != total {
            return Err(BackendError::Failure(format!(
                "{operation} completed {completed} of {total} primitives"
            )));
        }
        Ok(completed)
    }
}

#[cfg(target_os = "macos")]
impl Default for MacOsBackend {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(target_os = "macos")]
impl DesktopBackend for MacOsBackend {
    fn display_layout(&self) -> BackendResult<Value> {
        let output = self.helper("displays", "display_layout")?;
        let layout: Value =
            serde_json::from_str(&output).map_err(|_| BackendError::Unsupported {
                capability: "display_layout",
                message: "cghelper returned invalid display metadata".into(),
            })?;
        if !layout.is_object() || !layout["displays"].is_array() {
            return Err(BackendError::Unsupported {
                capability: "display_layout",
                message: "cghelper returned invalid display metadata".into(),
            });
        }
        Ok(layout)
    }

    fn active_window(&self) -> BackendResult<String> {
        if let Ok(name) = self.jxa(FRONTMOST_APP_SCRIPT)
            && !name.is_empty()
        {
            return Ok(name);
        }
        self.helper("frontmost", "active_window")
            .map_err(|error| match error {
                BackendError::Unsupported { message, .. } => BackendError::Unsupported {
                    capability: "active_window",
                    message,
                },
                other => other,
            })
    }

    fn app_matches(&self, requested: &str, actual: &str) -> bool {
        expected_app_name(requested).eq_ignore_ascii_case(actual.trim())
    }

    fn focus_app(&self, app: &str) -> BackendResult<String> {
        let app = app.trim();
        if app.is_empty() {
            return Err(BackendError::Failure(
                "app must be a non-empty application name or path".into(),
            ));
        }
        if let Ok(active) = self.active_window()
            && self.app_matches(app, &active)
        {
            return Ok(active);
        }
        self.activate(app).map_err(BackendError::Failure)?;
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
        let mut last = String::new();
        while std::time::Instant::now() < deadline {
            if let Ok(active) = self.active_window() {
                last = active;
                if self.app_matches(app, &last) {
                    return Ok(last);
                }
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        Err(BackendError::Focus(format!(
            "cannot verify focus for '{}'; frontmost app is '{}'",
            expected_app_name(app),
            if last.is_empty() { "unknown" } else { &last }
        )))
    }

    fn launch(&self, app: &str) -> BackendResult<String> {
        self.focus_app(app)
    }

    fn focused_element(&self) -> BackendResult<Value> {
        self.helper_json(&["focused".into()], "focused_element")
    }

    fn element_at(&self, x: i64, y: i64) -> BackendResult<Value> {
        self.helper_json(
            &["element".into(), x.to_string(), y.to_string()],
            "element_at",
        )
    }

    fn cursor_position(&self) -> BackendResult<(i64, i64)> {
        let position = self.helper("pos", "cursor_position")?;
        let values: Result<Vec<i64>, _> = position.split_whitespace().map(str::parse).collect();
        let values = values.map_err(|_| {
            BackendError::Failure("cghelper returned an invalid cursor position".into())
        })?;
        if values.len() != 2 {
            return Err(BackendError::Failure(
                "cghelper returned an invalid cursor position".into(),
            ));
        }
        Ok((values[0], values[1]))
    }

    fn move_path(
        &self,
        points: &[(i64, i64)],
        total_secs: f64,
        cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        let mut gap_us = (total_secs * 1_000_000.0 / points.len().max(1) as f64) as u64;
        if points.len() > 1 {
            gap_us = gap_us.max(2_000);
        }
        let body = points
            .iter()
            .map(|(x, y)| format!("{x} {y}\n"))
            .collect::<String>();
        self.input(
            &["movebatch".into(), gap_us.to_string()],
            Some(body.as_bytes()),
            "move",
            points.len(),
            cancelled,
        )?;
        Ok(())
    }

    fn click(
        &self,
        x: i64,
        y: i64,
        button: &str,
        double: bool,
        cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        let count = usize::from(double) + 1;
        self.input(
            &[
                "click".into(),
                x.to_string(),
                y.to_string(),
                if button == "right" { "1" } else { "0" }.into(),
                count.to_string(),
            ],
            None,
            "click",
            count,
            cancelled,
        )?;
        Ok(())
    }

    fn drag(
        &self,
        from: (i64, i64),
        to: (i64, i64),
        path: &[(i64, i64)],
        cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        let body = path
            .iter()
            .map(|(x, y)| format!("{x} {y}\n"))
            .collect::<String>();
        self.input(
            &[
                "drag".into(),
                from.0.to_string(),
                from.1.to_string(),
                to.0.to_string(),
                to.1.to_string(),
            ],
            Some(body.as_bytes()),
            "drag",
            path.len(),
            cancelled,
        )?;
        Ok(())
    }

    fn scroll(
        &self,
        direction: &str,
        amount: usize,
        cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<()> {
        let delta = if matches!(direction, "down" | "right") {
            -3
        } else {
            3
        };
        let (dy, dx) = if matches!(direction, "up" | "down") {
            (delta, 0)
        } else {
            (0, delta)
        };
        self.input(
            &[
                "scroll".into(),
                dy.to_string(),
                dx.to_string(),
                amount.max(1).to_string(),
            ],
            None,
            "scroll",
            amount,
            cancelled,
        )?;
        Ok(())
    }

    fn type_text(
        &self,
        text: &str,
        gaps: &[f64],
        cancelled: &dyn Fn() -> bool,
    ) -> BackendResult<usize> {
        let mean_us = if gaps.is_empty() {
            0
        } else {
            (gaps.iter().sum::<f64>() / gaps.len() as f64 * 1_000_000.0) as u64
        };
        self.input(
            &["type".into(), mean_us.to_string()],
            Some(text.as_bytes()),
            "type",
            text.chars().count(),
            cancelled,
        )
    }

    fn key(&self, keys: &str, cancelled: &dyn Fn() -> bool) -> BackendResult<()> {
        let (code, flags) = macos_key(keys)?;
        self.input(
            &["key".into(), code.to_string(), flags.to_string()],
            None,
            "key",
            1,
            cancelled,
        )?;
        Ok(())
    }

    fn release_all(&self) -> BackendResult<()> {
        self.input(&["release".into()], None, "release", 0, &|| false)?;
        Ok(())
    }

    fn capture_png(&self, x: i64, y: i64, width: i64, height: i64) -> BackendResult<Vec<u8>> {
        let image = self.helper_bytes(
            &[
                "capture".into(),
                x.to_string(),
                y.to_string(),
                width.to_string(),
                height.to_string(),
            ],
            "screen_capture",
        )?;
        if !image.starts_with(b"\x89PNG\r\n\x1a\n") {
            return Err(BackendError::Failure(
                "cghelper returned invalid PNG screenshot data".into(),
            ));
        }
        Ok(image)
    }

    fn backend_name(&self) -> &'static str {
        "macos"
    }

    fn helper_available(&self) -> BackendResult<bool> {
        Ok(self.helper.is_file())
    }

    fn accessibility_trusted(&self) -> BackendResult<bool> {
        Ok(self.helper("trusted", "accessibility")? == "1")
    }

    fn screen_recording_authorized(&self) -> BackendResult<bool> {
        Ok(self.helper("screen-recording", "screen_recording")? == "1")
    }

    fn capture_available(&self) -> BackendResult<bool> {
        Ok(self.helper.is_file())
    }

    fn list_apps(&self) -> BackendResult<Vec<String>> {
        let output = self
            .jxa(RUNNING_APPS_SCRIPT)
            .map_err(|_| BackendError::Unsupported {
                capability: "list_apps",
                message: "running application list is unavailable".into(),
            })?;
        let mut apps: Vec<String> =
            serde_json::from_str(&output).map_err(|_| BackendError::Unsupported {
                capability: "list_apps",
                message: "running application list is unavailable".into(),
            })?;
        apps.retain(|name| !name.trim().is_empty());
        apps.sort();
        apps.dedup();
        Ok(apps)
    }
}

#[cfg(target_os = "macos")]
fn command_output(command: &mut Command) -> Result<String, String> {
    let output = output_with_timeout(command, std::time::Duration::from_secs(60))?;
    if !output.status.success() {
        let message = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return Err(if message.is_empty() {
            format!("native command exited with {}", output.status)
        } else {
            message
        });
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

#[cfg(target_os = "macos")]
fn output_with_timeout(
    command: &mut Command,
    timeout: std::time::Duration,
) -> Result<std::process::Output, String> {
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| error.to_string())?;
    let mut stdout = child.stdout.take().expect("stdout was configured as piped");
    let mut stderr = child.stderr.take().expect("stderr was configured as piped");
    let deadline = std::time::Instant::now() + timeout;
    std::thread::scope(|scope| {
        let stdout_reader = scope.spawn(move || {
            let mut bytes = Vec::new();
            stdout.read_to_end(&mut bytes).map(|_| bytes)
        });
        let stderr_reader = scope.spawn(move || {
            let mut bytes = Vec::new();
            stderr.read_to_end(&mut bytes).map(|_| bytes)
        });
        let mut failure = None;
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) if std::time::Instant::now() < deadline => {
                    std::thread::sleep(std::time::Duration::from_millis(10));
                }
                Ok(None) => {
                    failure = Some(format!(
                        "native command timed out after {} seconds",
                        timeout.as_secs()
                    ));
                    let _ = child.kill();
                    break child.wait().map_err(|error| error.to_string())?;
                }
                Err(error) => {
                    failure = Some(error.to_string());
                    let _ = child.kill();
                    break child.wait().map_err(|wait_error| wait_error.to_string())?;
                }
            }
        };
        let stdout = stdout_reader
            .join()
            .map_err(|_| "native stdout reader panicked".to_owned())?
            .map_err(|error| error.to_string())?;
        let stderr = stderr_reader
            .join()
            .map_err(|_| "native stderr reader panicked".to_owned())?
            .map_err(|error| error.to_string())?;
        if let Some(failure) = failure {
            Err(failure)
        } else {
            Ok(std::process::Output {
                status,
                stdout,
                stderr,
            })
        }
    })
}

#[cfg(target_os = "macos")]
pub type NativeBackend = MacOsBackend;
#[cfg(not(target_os = "macos"))]
pub type NativeBackend = UnavailableBackend;

#[cfg(target_os = "macos")]
fn expected_app_name(app: &str) -> &str {
    let name = app.rsplit('/').next().unwrap_or(app);
    name.strip_suffix(".app")
        .or_else(|| name.strip_suffix(".APP"))
        .unwrap_or(name)
}

#[cfg(target_os = "macos")]
fn macos_key(keys: &str) -> BackendResult<(u16, u64)> {
    let mut flags = 0;
    let mut key = None;
    for part in keys.split(',') {
        match part {
            "cmd" => flags |= 1 << 20,
            "shift" => flags |= 1 << 17,
            "alt" => flags |= 1 << 19,
            "ctrl" => flags |= 1 << 18,
            "win" => {
                return Err(BackendError::Unsupported {
                    capability: "keyboard_input",
                    message: "win modifier is not supported on macOS".into(),
                });
            }
            ordinary => key = Some(ordinary),
        }
    }
    let key = key.ok_or_else(|| BackendError::Failure("key input has no ordinary key".into()))?;
    let code = match key {
        "return" | "enter" => 36,
        "escape" | "esc" => 53,
        "tab" => 48,
        "space" => 49,
        "delete" | "backspace" => 51,
        "forward_delete" => 117,
        "up" => 126,
        "down" => 125,
        "left" => 123,
        "right" => 124,
        "home" => 115,
        "end" => 119,
        "pageup" => 116,
        "pagedown" => 121,
        "f1" => 122,
        "f2" => 120,
        "f3" => 99,
        "f4" => 118,
        "f5" => 96,
        "f6" => 97,
        "f7" => 98,
        "f8" => 100,
        "f9" => 101,
        "f10" => 109,
        "f11" => 103,
        "f12" => 111,
        "a" => 0,
        "b" => 11,
        "c" => 8,
        "d" => 2,
        "e" => 14,
        "f" => 3,
        "g" => 5,
        "h" => 4,
        "i" => 34,
        "j" => 38,
        "k" => 40,
        "l" => 37,
        "m" => 46,
        "n" => 45,
        "o" => 31,
        "p" => 35,
        "q" => 12,
        "r" => 15,
        "s" => 1,
        "t" => 17,
        "u" => 32,
        "v" => 9,
        "w" => 13,
        "x" => 7,
        "y" => 16,
        "z" => 6,
        "1" => 18,
        "2" => 19,
        "3" => 20,
        "4" => 21,
        "5" => 23,
        "6" => 22,
        "7" => 26,
        "8" => 28,
        "9" => 25,
        "0" => 29,
        _ => return Err(BackendError::Failure(format!("unknown key: {key}"))),
    };
    Ok((code, flags))
}

#[cfg(all(test, target_os = "macos"))]
mod macos_tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::path::Path;

    fn executable(path: &Path, body: &str) {
        fs::write(path, body).expect("write fake native tool");
        let mut permissions = fs::metadata(path).unwrap().permissions();
        permissions.set_mode(0o700);
        fs::set_permissions(path, permissions).unwrap();
    }

    #[test]
    fn macos_adapter_exposes_read_only_desktop_state_through_the_provider_seam() {
        let fixture = std::env::temp_dir().join(format!(
            "computer-automation-provider-state-{}",
            std::process::id()
        ));
        fs::create_dir_all(&fixture).unwrap();
        let helper = fixture.join("cghelper");
        let osascript = fixture.join("osascript");
        executable(
            &helper,
            "#!/bin/sh\ncase \"$1\" in\n  displays) printf '%s\\n' '{\"origin\":[0,0],\"width\":1440,\"height\":900,\"displays\":[{\"id\":\"1\",\"origin\":[0,0],\"width\":1440,\"height\":900,\"scale\":[2.0,2.0],\"rotation\":0.0}]}' ;;\n  capture) printf '\\211PNG\\r\\n\\032\\nfixture' ;;\n  pos) printf '%s\\n' '4 5' ;;\n  movebatch|drag) awk 'END { print NR }' ;;\n  click) printf '%s\\n' \"$5\" ;;\n  scroll) printf '%s\\n' \"$4\" ;;\n  type) cat >/dev/null; printf '%s\\n' '2' ;;\n  key) printf '%s\\n' '1' ;;\n  release) exit 0 ;;\nesac\n",
        );
        executable(
            &osascript,
            "#!/bin/sh\ndir=${0%/*}\ncase \"$*\" in\n  *runningApplications*) printf '%s\\n' '[\"Safari\",\"Code\",\"Code\"]' ;;\n  *frontmostApplication*) if [ -f \"$dir/focused\" ]; then printf '%s\\n' 'Notes'; else printf '%s\\n' 'Code'; fi ;;\n  *Application*) : > \"$dir/focused\" ;;\nesac\n",
        );

        let backend = MacOsBackend::with_tools(helper, osascript);
        assert_eq!(backend.backend_name(), "macos");
        assert_eq!(backend.active_window().unwrap(), "Code");
        assert_eq!(backend.list_apps().unwrap(), vec!["Code", "Safari"]);
        assert_eq!(backend.display_layout().unwrap()["width"], 1440);
        assert!(
            backend
                .capture_png(1, 2, 3, 4)
                .unwrap()
                .starts_with(b"\x89PNG\r\n\x1a\n")
        );
        assert_eq!(backend.focus_app("Notes").unwrap(), "Notes");
        assert_eq!(backend.launch("Notes").unwrap(), "Notes");
        assert_eq!(backend.cursor_position().unwrap(), (4, 5));
        backend
            .move_path(&[(6, 7), (8, 9)], 0.004, &|| false)
            .unwrap();
        backend.click(8, 9, "left", true, &|| false).unwrap();
        backend
            .drag((8, 9), (10, 11), &[(9, 10), (10, 11)], &|| false)
            .unwrap();
        backend.scroll("down", 2, &|| false).unwrap();
        assert_eq!(backend.type_text("hi", &[0.0, 0.0], &|| false).unwrap(), 2);
        backend.key("cmd,a", &|| false).unwrap();
        backend.release_all().unwrap();

        fs::remove_dir_all(fixture).unwrap();
    }

    #[test]
    fn macos_adapter_interrupts_a_running_native_primitive_loop() {
        let fixture = std::env::temp_dir().join(format!(
            "computer-automation-provider-cancel-{}",
            std::process::id()
        ));
        fs::create_dir_all(&fixture).unwrap();
        let helper = fixture.join("cghelper");
        let osascript = fixture.join("osascript");
        executable(
            &helper,
            "#!/bin/sh\ntrap 'echo 1; exit 130' TERM\ncat >/dev/null\nwhile :; do :; done\n",
        );
        executable(&osascript, "#!/bin/sh\nexit 0\n");
        let backend = MacOsBackend::with_tools(helper, osascript);
        let started = std::time::Instant::now();
        let error = backend
            .move_path(&[(1, 1), (2, 2)], 1.0, &|| {
                started.elapsed() >= std::time::Duration::from_millis(20)
            })
            .unwrap_err();
        assert!(started.elapsed() < std::time::Duration::from_secs(2));
        assert!(
            matches!(
                &error,
                BackendError::Cancelled {
                    operation,
                    completed: 0,
                    total: 2
                } if operation == "move"
            ),
            "{error:?}"
        );
        fs::remove_dir_all(fixture).unwrap();
    }
}
