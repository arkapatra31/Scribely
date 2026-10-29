//! Native extras: the tray / menu-bar icon, the global start/stop shortcut, and keeping the
//! app running in the tray when its window is closed.
//!
//! The UI owns the recorder (it talks to the backend), so tray and shortcut actions are sent
//! to it as a `shell-action` event; it reports the recorder's state back through
//! `set_tray_state` so the menu reads "Start" / "Stop" / "Pause" / "Resume" correctly.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{App, AppHandle, Emitter, Manager, Wry};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

/// Start/stop recording from anywhere. Shown in the UI as ⌘⇧⌥R / Ctrl+Shift+Alt+R.
pub const SHORTCUT: &str = "CommandOrControl+Shift+Alt+R";

pub struct Tray {
    icon: TrayIcon<Wry>,
    record: MenuItem<Wry>,
    pause: MenuItem<Wry>,
}

/// None when there is no tray icon (Linux, or the system refused one).
pub struct TrayState(Option<Tray>);

impl TrayState {
    pub fn is_shown(&self) -> bool {
        self.0.is_some()
    }
}

pub fn shortcut_plugin() -> tauri::plugin::TauriPlugin<Wry> {
    tauri_plugin_global_shortcut::Builder::new()
        .with_handler(|app, _shortcut, event| {
            if event.state == ShortcutState::Pressed {
                send(app, "toggle-recording");
            }
        })
        .build()
}

pub fn setup(app: &mut App) {
    // Another app may own the shortcut already; Scribely works without it.
    if let Err(err) = app.global_shortcut().register(SHORTCUT) {
        eprintln!("[scribely] couldn't register the {SHORTCUT} shortcut: {err}");
    }
    // Scribely targets macOS and Windows. On Linux (dev/CI only) the tray library aborts the
    // app when libappindicator is missing, so it's skipped there.
    let tray = if cfg!(target_os = "linux") {
        None
    } else {
        build_tray(app)
            .inspect_err(|err| eprintln!("[scribely] no tray icon: {err}"))
            .ok()
    };
    app.manage(TrayState(tray));
}

fn build_tray(app: &mut App) -> tauri::Result<Tray> {
    let record = MenuItem::with_id(app, "record", "Start recording", false, Some(SHORTCUT))?;
    let pause = MenuItem::with_id(app, "pause", "Pause", false, None::<&str>)?;
    let show = MenuItem::with_id(app, "show", "Show Scribely", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Scribely", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&record, &pause, &separator, &show, &quit])?;

    let mut builder = TrayIconBuilder::with_id("scribely")
        .tooltip("Scribely")
        .menu(&menu)
        // Windows convention: left click opens the window, right click the menu.
        .show_menu_on_left_click(cfg!(not(windows)))
        .on_menu_event(|app, event| match event.id.as_ref() {
            "record" => send(app, "toggle-recording"),
            "pause" => send(app, "toggle-pause"),
            "show" => show_main_window(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
                && cfg!(windows)
            {
                show_main_window(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    let icon = builder.build(app)?;
    Ok(Tray {
        icon,
        record,
        pause,
    })
}

/// Called by the UI whenever the recorder changes: "idle", "recording", "paused" or "busy".
#[tauri::command]
pub fn set_tray_state(state: &str, tray: tauri::State<'_, TrayState>) -> Result<(), String> {
    let Some(tray) = &tray.0 else {
        return Ok(());
    };
    let (record, record_on) = match state {
        "recording" | "paused" => ("Stop recording", true),
        "idle" => ("Start recording", true),
        _ => ("Start recording", false),
    };
    let (pause, pause_on) = match state {
        "recording" => ("Pause", true),
        "paused" => ("Resume", true),
        _ => ("Pause", false),
    };
    let (tooltip, title) = match state {
        "recording" => ("Scribely — recording", Some("●")),
        "paused" => ("Scribely — paused", Some("❚❚")),
        _ => ("Scribely", None),
    };
    let apply = || -> tauri::Result<()> {
        tray.record.set_text(record)?;
        tray.record.set_enabled(record_on)?;
        tray.pause.set_text(pause)?;
        tray.pause.set_enabled(pause_on)?;
        tray.icon.set_tooltip(Some(tooltip))?;
        // Text next to the icon in the macOS menu bar (ignored elsewhere).
        tray.icon.set_title(title)?;
        Ok(())
    };
    apply().map_err(|err| err.to_string())
}

pub fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn send(app: &AppHandle, action: &str) {
    if let Err(err) = app.emit("shell-action", action) {
        eprintln!("[scribely] couldn't send {action} to the window: {err}");
    }
}
