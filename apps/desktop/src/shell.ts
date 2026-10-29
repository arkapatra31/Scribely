// The bits of the native shell (Tauri) the UI uses: tray/shortcut actions in, recording state
// out. In a plain browser (e.g. `vite` without Tauri) these are no-ops.
import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

/** Sent by the tray menu and the global shortcut. */
export type ShellAction = "toggle-recording" | "toggle-pause";

/** The global start/stop shortcut, as registered in src-tauri/src/lib.rs. */
export const SHORTCUT_LABEL = /Mac/.test(navigator.userAgent) ? "⌘⇧⌥R" : "Ctrl+Shift+Alt+R";

export function onShellAction(handler: (action: ShellAction) => void): () => void {
  if (!isTauri()) return () => {};
  const unlisten = listen<ShellAction>("shell-action", (event) => handler(event.payload));
  return () => void unlisten.then((stop) => stop());
}

/** Keep the tray menu and icon in step with the recorder. */
export function setTrayState(state: "idle" | "recording" | "paused" | "busy"): void {
  if (isTauri()) void invoke("set_tray_state", { state }).catch(() => {});
}
