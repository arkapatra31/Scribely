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

pub fn shortcut_plugin() -> tauri::plugin::TauriPlugin<Wry> {
    tauri_plugin_global_shortcut::Builder::new()
        .with_handler(|app, _shortcut, event| {
            if event.state == ShortcutState::Pressed {
                send(app, "toggle-recording");
            }
        })
        .build()
}

pub fn setup(app: &mut App) -> tauri::Result<()> {
    // Another app may own the shortcut already; Scribely works without it.
    if let Err(err) = app.global_shortcut().register(SHORTCUT) {
        eprintln!("[scribely] couldn't register the {SHORTCUT} shortcut: {err}");
    }

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
    app.manage(Tray { icon, record, pause });
    Ok(())
}

/// Called by the UI whenever the recorder changes: "idle", "recording", "paused" or "busy".
#[tauri::command]
pub fn set_tray_state(state: &str, tray: tauri::State<'_, Tray>) -> Result<(), String> {
    let (record, record_on, pause, pause_on, tooltip, title) = match state {
        "recording" => ("Stop recording", true, "Pause", true, "Scribely — recording", "●"),
        "paused" => ("Stop recording", true, "Resume", true, "Scribely — paused", "❚❚"),
        "idle" => ("Start recording", true, "Pause", false, "Scribely", ""),
        _ => ("Start recording", false, "Pause", false, "Scribely", ""),
    };
    let apply = || -> tauri::Result<()> {
        tray.record.set_text(record)?;
        tray.record.set_enabled(record_on)?;
        tray.pause.set_text(pause)?;
        tray.pause.set_enabled(pause_on)?;
        tray.icon.set_tooltip(Some(tooltip))?;
        // Text next to the icon in the macOS menu bar (ignored elsewhere).
        tray.icon.set_title(if title.is_empty() { None } else { Some(title) })?;
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
