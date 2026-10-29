mod backend;
mod shell;

use std::process::Child;
use std::sync::Mutex;

use tauri::{Manager, RunEvent, WindowEvent};

/// The backend process this app started (None if it reused one already running).
struct Backend(Mutex<Option<Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(shell::shortcut_plugin())
        .setup(|app| {
            app.manage(Backend(Mutex::new(backend::start())));
            shell::setup(app);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![shell::set_tray_state])
        .on_window_event(|window, event| {
            // Closing the window keeps Scribely in the tray, so a recording (and the shortcut)
            // keeps working. Quit from the tray menu or with ⌘Q. Without a tray, close quits.
            if let WindowEvent::CloseRequested { api, .. } = event
                && window.state::<shell::TrayState>().is_shown()
            {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|handle, event| match event {
        // macOS: clicking the Dock icon brings the hidden window back.
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => shell::show_main_window(handle),
        RunEvent::Exit => {
            if let Some(child) = handle
                .state::<Backend>()
                .0
                .lock()
                .ok()
                .and_then(|mut c| c.take())
            {
                backend::stop(child);
            }
        }
        _ => {}
    });
}
