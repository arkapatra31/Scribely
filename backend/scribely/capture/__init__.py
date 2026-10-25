"""Platform audio capture: one async interface over WASAPI, ScreenCaptureKit, and WAV files."""

from __future__ import annotations

import sys

from scribely.capture.base import AudioCapture, AudioChunk, CaptureError, CapturePermissionError
from scribely.capture.dsp import TARGET_SAMPLE_RATE
from scribely.config import CaptureConfig

__all__ = [
    "TARGET_SAMPLE_RATE",
    "AudioCapture",
    "AudioChunk",
    "CaptureError",
    "CapturePermissionError",
    "create_capture",
]

_AUTO_BACKENDS = {"win32": "wasapi", "darwin": "screencapturekit"}


def create_capture(cfg: CaptureConfig, *, platform: str = sys.platform) -> AudioCapture:
    backend: str = cfg.backend
    if backend == "auto":
        if platform not in _AUTO_BACKENDS:
            raise CaptureError(
                "System audio capture is supported on Windows and macOS only. To try Scribely "
                'elsewhere, set backend = "file" and file_path under [capture] in config.toml.'
            )
        backend = _AUTO_BACKENDS[platform]

    kwargs = {"max_queue_seconds": cfg.max_queue_seconds}
    if backend == "file":
        from scribely.capture.file import FileCapture

        assert cfg.file_path is not None  # enforced by CaptureConfig
        return FileCapture(cfg.file_path, realtime=cfg.file_realtime, **kwargs)
    if backend == "wasapi":
        from scribely.capture.wasapi import WasapiLoopbackCapture

        return WasapiLoopbackCapture(**kwargs)
    from scribely.capture.screencapturekit import ScreenCaptureKitCapture

    return ScreenCaptureKitCapture(**kwargs)
