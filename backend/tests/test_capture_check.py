import wave
from pathlib import Path

import numpy as np
import pytest

from scribely.capture import check
from scribely.capture.check import main
from tests.audio import sine, write_wav


def use_file_backend(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("SCRIBELY_CAPTURE__BACKEND", "file")
    monkeypatch.setenv("SCRIBELY_CAPTURE__FILE_PATH", str(path))
    monkeypatch.setenv("SCRIBELY_CAPTURE__FILE_REALTIME", "false")


def test_records_to_16k_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use_file_backend(monkeypatch, write_wav(tmp_path / "in.wav", sine(440, 1.5, 48_000), 48_000))
    out = tmp_path / "out.wav"
    main(["--seconds", "5", "--output", str(out)])
    with wave.open(str(out)) as wav:
        assert wav.getframerate() == 16_000
        assert wav.getnchannels() == 1
        assert abs(wav.getnframes() - 24_000) <= 2
    assert "Level: RMS" in capsys.readouterr().out


def test_silent_recording_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    silent = np.zeros(16_000, dtype=np.float32)
    use_file_backend(monkeypatch, write_wav(tmp_path / "in.wav", silent, 16_000))
    with pytest.raises(SystemExit) as exc:
        main(["--seconds", "5", "--output", str(tmp_path / "out.wav")])
    assert exc.value.code == 1


def test_capture_error_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # create_capture's platform default is bound at import, so pass one explicitly.
    from scribely.capture import create_capture as real

    monkeypatch.setattr(check, "create_capture", lambda cfg: real(cfg, platform="linux"))
    with pytest.raises(SystemExit) as exc:
        main(["--seconds", "1"])
    assert exc.value.code == 2
    assert "Windows and macOS only" in capsys.readouterr().err
