"""The OS permission system-audio capture needs (macOS: Screen & System Audio Recording)."""

from __future__ import annotations

import subprocess
import sys

from scribely.models import CapturePermissionState

MACOS_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


def check(platform: str = sys.platform) -> tuple[CapturePermissionState, str]:
    """The current state and a plain-language explanation."""
    if platform == "win32":
        return "not_needed", "Windows lets Scribely hear system audio without a permission."
    if platform != "darwin":
        return "unknown", "System audio capture works on macOS and Windows."
    if _quartz_preflight():
        return "granted", "Scribely can hear your computer's audio."
    return "denied", (
        "Scribely needs the Screen & System Audio Recording permission to hear audio, even "
        "though it never records the screen. Allow it, then restart Scribely."
    )


def request(platform: str = sys.platform) -> None:
    """Show the system prompt (macOS shows it once; after that, use System Settings)."""
    if platform == "darwin":
        import Quartz

        Quartz.CGMainDisplayID()
        Quartz.CGRequestScreenCaptureAccess()


def open_settings(platform: str = sys.platform) -> None:
    if platform == "darwin":
        subprocess.Popen(
            ["open", MACOS_SETTINGS_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )


def _quartz_preflight() -> bool:
    import Quartz

    Quartz.CGMainDisplayID()  # initialise the CoreGraphics connection for a non-app process
    return bool(Quartz.CGPreflightScreenCaptureAccess())
