use serde::{Deserialize, Serialize};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

#[cfg(unix)]
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};

static FRAME_SEQUENCE: AtomicU64 = AtomicU64::new(0);
static RUNTIME_SEQUENCE: AtomicU64 = AtomicU64::new(0);
const FRAME_METADATA_BUDGET: usize = 256;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct Display {
    pub id: serde_json::Value,
    pub origin: [i64; 2],
    pub width: i64,
    pub height: i64,
    pub scale: [f64; 2],
    pub rotation: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct DisplayLayout {
    pub origin: [i64; 2],
    pub width: i64,
    pub height: i64,
    pub displays: Vec<Display>,
}

impl DisplayLayout {
    pub fn validate(&self) -> Result<(), String> {
        if self.width <= 0 || self.height <= 0 || self.displays.is_empty() {
            return Err(
                "display layout must have positive bounds and contain at least one display".into(),
            );
        }
        let mut min_x = i64::MAX;
        let mut min_y = i64::MAX;
        let mut max_x = i64::MIN;
        let mut max_y = i64::MIN;
        for display in &self.displays {
            if display.width <= 0
                || display.height <= 0
                || !display
                    .scale
                    .iter()
                    .all(|scale| scale.is_finite() && *scale > 0.0)
                || !display.rotation.is_finite()
            {
                return Err("display bounds, scale, and rotation must be valid".into());
            }
            let right = display.origin[0]
                .checked_add(display.width)
                .ok_or("display bounds overflow")?;
            let bottom = display.origin[1]
                .checked_add(display.height)
                .ok_or("display bounds overflow")?;
            min_x = min_x.min(display.origin[0]);
            min_y = min_y.min(display.origin[1]);
            max_x = max_x.max(right);
            max_y = max_y.max(bottom);
        }
        if self.origin != [min_x, min_y]
            || self.width != max_x.checked_sub(min_x).ok_or("layout bounds overflow")?
            || self.height != max_y.checked_sub(min_y).ok_or("layout bounds overflow")?
        {
            return Err("display layout bounds do not match its displays".into());
        }
        Ok(())
    }

    pub fn contains_point(&self, x: i64, y: i64) -> bool {
        self.displays.iter().any(|display| {
            x >= display.origin[0]
                && y >= display.origin[1]
                && display.origin[0]
                    .checked_add(display.width)
                    .is_some_and(|right| x < right)
                && display.origin[1]
                    .checked_add(display.height)
                    .is_some_and(|bottom| y < bottom)
        })
    }

    fn contains_region(&self, region: (i64, i64, i64, i64)) -> bool {
        let (x, y, width, height) = region;
        width > 0
            && height > 0
            && x >= self.origin[0]
            && y >= self.origin[1]
            && x.checked_add(width)
                .zip(self.origin[0].checked_add(self.width))
                .is_some_and(|(right, edge)| right <= edge)
            && y.checked_add(height)
                .zip(self.origin[1].checked_add(self.height))
                .is_some_and(|(bottom, edge)| bottom <= edge)
    }
}

#[derive(Debug)]
pub struct Frame {
    pub id: String,
    pub layout: DisplayLayout,
    pub region: (i64, i64, i64, i64),
    pub active_window: String,
    image: Option<Vec<u8>>,
    path: Option<PathBuf>,
}

impl Frame {
    pub fn image(&self) -> Option<&[u8]> {
        self.image.as_deref()
    }

    pub fn path(&self) -> Option<&Path> {
        self.path.as_deref()
    }
}

#[derive(Debug)]
pub struct FrameStore {
    max_bytes: usize,
    frame: Option<Frame>,
    runtime_dir: Option<PathBuf>,
}

impl FrameStore {
    pub fn new(max_bytes: usize) -> Result<Self, String> {
        if max_bytes == 0 {
            return Err("max_bytes must be positive".into());
        }
        Ok(Self {
            max_bytes,
            frame: None,
            runtime_dir: None,
        })
    }

    pub fn insert(
        &mut self,
        layout: DisplayLayout,
        region: (i64, i64, i64, i64),
        active_window: impl Into<String>,
        image: Option<Vec<u8>>,
    ) -> Result<&Frame, String> {
        self.validate_candidate(&layout, region, image.as_ref().map_or(0, Vec::len))?;
        Ok(self.replace_frame(layout, region, active_window.into(), image, None))
    }

    pub fn insert_path(
        &mut self,
        layout: DisplayLayout,
        region: (i64, i64, i64, i64),
        active_window: impl Into<String>,
        image: &[u8],
    ) -> Result<&Frame, String> {
        self.validate_candidate(&layout, region, image.len())?;
        let path = self.replace_path(image)?;
        Ok(self.replace_frame(layout, region, active_window.into(), None, Some(path)))
    }

    fn validate_candidate(
        &self,
        layout: &DisplayLayout,
        region: (i64, i64, i64, i64),
        image_bytes: usize,
    ) -> Result<(), String> {
        layout.validate()?;
        if !layout.contains_region(region) {
            return Err("capture region is outside the current display layout".into());
        }
        let retained_bytes = image_bytes
            .checked_add(FRAME_METADATA_BUDGET)
            .ok_or("frame byte count overflow")?;
        if retained_bytes > self.max_bytes {
            return Err(format!(
                "frame too_large: result uses {retained_bytes} bytes; limit is {}",
                self.max_bytes
            ));
        }
        Ok(())
    }

    fn replace_frame(
        &mut self,
        layout: DisplayLayout,
        region: (i64, i64, i64, i64),
        active_window: String,
        image: Option<Vec<u8>>,
        path: Option<PathBuf>,
    ) -> &Frame {
        if path.is_none() {
            self.drop_path();
        }
        let id = FRAME_SEQUENCE.fetch_add(1, Ordering::Relaxed) + 1;
        self.frame = Some(Frame {
            id: format!("frame-{id}"),
            layout,
            region,
            active_window,
            image,
            path,
        });
        self.frame.as_ref().expect("frame was just inserted")
    }

    fn replace_path(&mut self, image: &[u8]) -> Result<PathBuf, String> {
        let directory = match self.runtime_dir.as_ref() {
            Some(directory) => directory.clone(),
            None => {
                let directory = create_runtime_dir()?;
                self.runtime_dir = Some(directory.clone());
                directory
            }
        };
        let target = directory.join("current.png");
        let temporary = directory.join(format!(
            ".current-{}.tmp",
            RUNTIME_SEQUENCE.fetch_add(1, Ordering::Relaxed) + 1
        ));
        let result = (|| {
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            options.mode(0o600);
            let mut file = options
                .open(&temporary)
                .map_err(|error| format!("cannot create private screenshot: {error}"))?;
            file.write_all(image)
                .and_then(|_| file.sync_all())
                .map_err(|error| format!("cannot write private screenshot: {error}"))?;
            fs::rename(&temporary, &target)
                .map_err(|error| format!("cannot replace private screenshot: {error}"))?;
            let metadata = fs::symlink_metadata(&target)
                .map_err(|error| format!("cannot inspect private screenshot: {error}"))?;
            if !metadata.file_type().is_file() {
                return Err("screenshot path is not a regular owner file".into());
            }
            #[cfg(unix)]
            if metadata.permissions().mode() & 0o077 != 0 {
                return Err("screenshot path is not owner-private".into());
            }
            Ok(target.clone())
        })();
        let _ = fs::remove_file(&temporary);
        result
    }

    fn drop_path(&mut self) {
        if let Some(path) = self.frame.as_ref().and_then(|frame| frame.path.as_ref()) {
            let _ = fs::remove_file(path);
        }
    }

    pub fn preflight_capture(
        &self,
        width: i64,
        height: i64,
        include_base64: bool,
    ) -> Result<(), String> {
        let width = usize::try_from(width).map_err(|_| "capture width must be positive")?;
        let height = usize::try_from(height).map_err(|_| "capture height must be positive")?;
        if width == 0 || height == 0 {
            return Err("capture width/height must be positive".into());
        }
        let pixels = width
            .checked_mul(height)
            .ok_or("capture dimensions overflow")?;
        let raw = pixels.checked_mul(4).ok_or("capture byte count overflow")?;
        let png_bound = raw
            .checked_add(raw / 100)
            .and_then(|bytes| bytes.checked_add(65_536))
            .ok_or("capture byte count overflow")?;
        let base64 = if include_base64 {
            png_bound
                .checked_add(2)
                .and_then(|bytes| bytes.checked_div(3))
                .and_then(|groups| groups.checked_mul(4))
                .ok_or("capture byte count overflow")?
        } else {
            0
        };
        let total = raw
            .checked_add(png_bound)
            .and_then(|bytes| bytes.checked_add(base64))
            .and_then(|bytes| bytes.checked_add(FRAME_METADATA_BUDGET))
            .ok_or("capture byte count overflow")?;
        if total > self.max_bytes {
            return Err(format!(
                "frame too_large: needs at most {total} bytes; limit is {}",
                self.max_bytes
            ));
        }
        Ok(())
    }

    pub fn latest(&self) -> Option<&Frame> {
        self.frame.as_ref()
    }

    pub fn get(&self, id: &str) -> Option<&Frame> {
        self.frame.as_ref().filter(|frame| frame.id == id)
    }

    pub fn len(&self) -> usize {
        usize::from(self.frame.is_some())
    }

    pub fn is_empty(&self) -> bool {
        self.frame.is_none()
    }

    pub fn clear(&mut self) {
        self.drop_path();
        self.frame = None;
        if let Some(directory) = self.runtime_dir.take() {
            let _ = fs::remove_dir(directory);
        }
    }

    pub fn authorizes(
        &self,
        id: &str,
        current_layout: &DisplayLayout,
        active_window: &str,
        targets: &[(i64, i64)],
    ) -> bool {
        let Some(frame) = self.get(id) else {
            return false;
        };
        if frame.layout != *current_layout || frame.active_window != active_window {
            return false;
        }
        let (left, top, width, height) = frame.region;
        targets.iter().all(|(x, y)| {
            x >= &left
                && y >= &top
                && left.checked_add(width).is_some_and(|right| x < &right)
                && top.checked_add(height).is_some_and(|bottom| y < &bottom)
                && current_layout.contains_point(*x, *y)
        })
    }
}

impl Drop for FrameStore {
    fn drop(&mut self) {
        self.clear();
    }
}

fn create_runtime_dir() -> Result<PathBuf, String> {
    for _ in 0..1000 {
        let nonce = RUNTIME_SEQUENCE.fetch_add(1, Ordering::Relaxed) + 1;
        let directory = std::env::temp_dir().join(format!(
            "computer-automation-{}-{nonce}",
            std::process::id()
        ));
        match fs::create_dir(&directory) {
            Ok(()) => {
                #[cfg(unix)]
                if let Err(error) =
                    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700))
                {
                    let _ = fs::remove_dir(&directory);
                    return Err(format!("cannot secure screenshot directory: {error}"));
                }
                return Ok(directory);
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(format!("cannot create screenshot directory: {error}")),
        }
    }
    Err("cannot allocate a private screenshot directory".into())
}
