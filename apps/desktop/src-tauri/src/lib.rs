mod backend;

use std::process::Child;
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

/// The backend process this app started (None if it reused one already running).
struct Backend(Mutex<Option<Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            app.manage(Backend(Mutex::new(backend::start())));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|handle, event| {
        if let RunEvent::Exit = event
            && let Some(child) = handle
                .state::<Backend>()
                .0
                .lock()
                .ok()
                .and_then(|mut c| c.take())
        {
            backend::stop(child);
        }
    });
}
