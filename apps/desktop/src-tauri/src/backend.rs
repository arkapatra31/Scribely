//! Launches the Python backend (the sidecar) with the app and stops it on quit.
//!
//! Which backend runs, in order:
//! 1. `SCRIBELY_BACKEND_CMD` (e.g. `uv run scribely-backend`), for custom setups;
//! 2. a bundled `scribely-backend` executable next to the app (release builds, Phase 11);
//! 3. in debug builds, `uv run scribely-backend` in the repo's `backend/` folder.
//!
//! If something already listens on the backend port (e.g. a backend started by hand in a
//! terminal), the app uses it and starts nothing. The backend also watches our pid
//! (`SCRIBELY_PARENT_PID`) and exits by itself if the app crashes.

use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::Duration;

/// Must match the WebSocket URL the UI connects to (`ws://127.0.0.1:8765/ws`).
pub const PORT: u16 = 8765;

pub fn start() -> Option<Child> {
    if port_in_use(PORT) {
        eprintln!("[scribely] a backend is already running on port {PORT}; using it");
        return None;
    }
    let Some(mut command) = backend_command() else {
        eprintln!(
            "[scribely] no backend to start: set SCRIBELY_BACKEND_CMD or run \
             `uv run scribely-backend` in the backend folder"
        );
        return None;
    };
    command
        .env("SCRIBELY_PARENT_PID", std::process::id().to_string())
        .env("SCRIBELY_SERVER__PORT", PORT.to_string())
        .stdin(Stdio::null());
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        // Own process group, so quitting stops `uv` *and* the Python process under it.
        command.process_group(0);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    match command.spawn() {
        Ok(child) => {
            eprintln!("[scribely] started backend (pid {})", child.id());
            Some(child)
        }
        Err(err) => {
            eprintln!("[scribely] couldn't start the backend: {err}");
            None
        }
    }
}

/// Graceful stop (lets the backend finish a recording and close the database), then force.
pub fn stop(mut child: Child) {
    terminate(&child, false);
    for _ in 0..80 {
        if matches!(child.try_wait(), Ok(Some(_))) {
            return;
        }
        thread::sleep(Duration::from_millis(100));
    }
    eprintln!("[scribely] backend didn't stop in time; killing it");
    terminate(&child, true);
    let _ = child.kill();
    let _ = child.wait();
}

fn backend_command() -> Option<Command> {
    if let Ok(custom) = std::env::var("SCRIBELY_BACKEND_CMD") {
        let mut parts = custom.split_whitespace();
        let mut command = Command::new(parts.next()?);
        command.args(parts);
        return Some(command);
    }

    // Release builds: Tauri's `externalBin` puts the bundled backend next to the app binary.
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let bundled = exe_dir.join(if cfg!(windows) {
        "scribely-backend.exe"
    } else {
        "scribely-backend"
    });
    if bundled.is_file() {
        return Some(Command::new(bundled));
    }

    // Development: the source checkout this binary was built from.
    if cfg!(debug_assertions) {
        let backend_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../backend");
        if backend_dir.join("pyproject.toml").is_file() {
            let mut command = Command::new("uv");
            command
                .args(["run", "scribely-backend"])
                .current_dir(backend_dir);
            return Some(command);
        }
    }
    None
}

fn port_in_use(port: u16) -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
}

#[cfg(unix)]
fn terminate(child: &Child, force: bool) {
    let signal = if force { "-KILL" } else { "-TERM" };
    // A negative pid targets the whole process group created in `start`; `--` stops `kill`
    // from reading it as an option.
    let _ = Command::new("kill")
        .args([signal, "--", &format!("-{}", child.id())])
        .stderr(Stdio::null())
        .status();
}

#[cfg(windows)]
fn terminate(child: &Child, _force: bool) {
    // Windows has no SIGTERM for console processes; end the process tree. SQLite (WAL) is
    // crash-safe, so at most the last second of a running recording is lost.
    let _ = Command::new("taskkill")
        .args(["/PID", &child.id().to_string(), "/T", "/F"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;

    #[test]
    fn detects_listening_and_free_ports() {
        // One test, so a parallel test can't grab the freed port in between.
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        assert!(port_in_use(listener.local_addr().unwrap().port()));
        let free = TcpListener::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port();
        assert!(!port_in_use(free));
    }

    #[test]
    fn dev_builds_find_the_repo_backend() {
        let backend = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../backend");
        assert!(backend.join("pyproject.toml").is_file());
    }

    #[cfg(unix)]
    #[test]
    fn stop_ends_the_whole_process_group() {
        // A shell that starts a grandchild, like `uv` starting Python.
        let mut command = Command::new("sh");
        command.args(["-c", "sleep 60 & wait"]);
        {
            use std::os::unix::process::CommandExt;
            command.process_group(0);
        }
        let child = command.spawn().unwrap();
        let pgid = child.id();
        thread::sleep(Duration::from_millis(200));
        let started = std::time::Instant::now();
        stop(child);
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "graceful stop timed out"
        );
        // Orphans may linger briefly as zombies until init reaps them; only live ones count.
        let mut live = usize::MAX;
        for _ in 0..20 {
            let ps = Command::new("ps")
                .args(["-eo", "pgid=,stat="])
                .output()
                .unwrap();
            live = String::from_utf8_lossy(&ps.stdout)
                .lines()
                .filter_map(|l| {
                    l.split_whitespace()
                        .collect::<Vec<_>>()
                        .get(..2)
                        .map(<[_]>::to_vec)
                })
                .filter(|cols| cols[0] == pgid.to_string() && !cols[1].starts_with('Z'))
                .count();
            if live == 0 {
                break;
            }
            thread::sleep(Duration::from_millis(100));
        }
        assert_eq!(live, 0, "processes in the group are still running");
    }
}
