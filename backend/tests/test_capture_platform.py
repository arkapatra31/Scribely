import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from scribely.capture import CaptureError, CapturePermissionError, create_capture
from scribely.capture.file import FileCapture
from scribely.capture.screencapturekit import (
    ScreenCaptureKitCapture,
    _sample_buffer_to_frames,
    _translate_error,
)
from scribely.capture.wasapi import WasapiLoopbackCapture
from scribely.config import CaptureConfig, ConfigError, load_settings


def test_auto_picks_platform_backend() -> None:
    cfg = CaptureConfig()
    assert isinstance(create_capture(cfg, platform="win32"), WasapiLoopbackCapture)
    assert isinstance(create_capture(cfg, platform="darwin"), ScreenCaptureKitCapture)


def test_auto_on_unsupported_platform_is_actionable() -> None:
    with pytest.raises(CaptureError, match='backend = "file"'):
        create_capture(CaptureConfig(), platform="linux")


def test_file_backend(tmp_path: Path) -> None:
    cfg = CaptureConfig(backend="file", file_path=tmp_path / "a.wav")
    assert isinstance(create_capture(cfg), FileCapture)


def test_file_backend_requires_path(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_text('[capture]\nbackend = "file"\n')
    with pytest.raises(ConfigError, match="requires file_path"):
        load_settings(path)


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="non-Windows behaviour")
def test_wasapi_off_windows_is_actionable() -> None:
    with pytest.raises(CaptureError, match="only available on Windows"):
        asyncio.run(WasapiLoopbackCapture().start())


@pytest.mark.skipif(__import__("sys").platform == "darwin", reason="non-macOS behaviour")
def test_screencapturekit_off_macos_is_actionable() -> None:
    with pytest.raises(CaptureError, match="needs macOS 13"):
        asyncio.run(ScreenCaptureKitCapture().start())


class FakeCoreMedia:
    """Mimics the PyObjC CoreMedia calls used to unpack a ScreenCaptureKit audio buffer."""

    def __init__(self, data: bytes, n_frames: int, status: int = 0) -> None:
        self.data, self.n_frames, self.status = data, n_frames, status

    def CMSampleBufferIsValid(self, buf: Any) -> bool:
        return True

    def CMSampleBufferGetNumSamples(self, buf: Any) -> int:
        return self.n_frames

    def CMSampleBufferGetDataBuffer(self, buf: Any) -> object:
        return object()

    def CMBlockBufferGetDataLength(self, block: Any) -> int:
        return len(self.data)

    def CMBlockBufferCopyDataBytes(self, block: Any, offset: int, length: int, dest: Any) -> Any:
        return self.status, self.data


def test_sample_buffer_planar_stereo_to_frames() -> None:
    planar = np.array([0.1, 0.2, 0.3, -0.1, -0.2, -0.3], dtype="<f4").tobytes()
    frames = _sample_buffer_to_frames(FakeCoreMedia(planar, 3), object())
    assert frames.shape == (3, 2)
    np.testing.assert_allclose(frames[:, 1], [-0.1, -0.2, -0.3], rtol=1e-6)


def test_sample_buffer_read_failure() -> None:
    with pytest.raises(CaptureError, match="OSStatus -12700"):
        _sample_buffer_to_frames(FakeCoreMedia(b"\0" * 8, 1, status=-12700), object())


def _ns_error(code: int, text: str) -> Any:
    return SimpleNamespace(code=lambda: code, localizedDescription=lambda: text)


def test_declined_permission_maps_to_permission_error() -> None:
    err = _translate_error(_ns_error(-3801, "declined"), "ctx")
    assert isinstance(err, CapturePermissionError)
    assert "Privacy & Security" in str(err)


def test_other_errors_keep_context() -> None:
    err = _translate_error(_ns_error(-3802, "No display"), "Couldn't start")
    assert not isinstance(err, CapturePermissionError)
    assert str(err) == "Couldn't start: No display"
