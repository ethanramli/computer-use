pub mod cli;
mod controller;
pub mod frames;
pub mod mcp;
pub mod motion;
pub mod protocol;
mod provider;
mod safety;
pub mod timing;
pub(crate) mod validation;

pub use controller::{CancellationHandle, Controller};
#[cfg(target_os = "macos")]
pub use provider::MacOsBackend;
pub use provider::{
    BackendError, BackendResult, DesktopBackend, MockBackend, NativeBackend, UnavailableBackend,
};
