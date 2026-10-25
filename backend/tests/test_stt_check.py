import pytest

from scribely.stt.check import Printer, fmt_time, main
from scribely.stt.stream import Utterance


def test_fmt_time() -> None:
    assert fmt_time(0) == "00:00.0"
    assert fmt_time(75.25) == "01:15.2"


def test_printer_replaces_partials_with_final(capsys: pytest.CaptureFixture[str]) -> None:
    p = Printer()
    p.show(Utterance(0, 1, "hel", False))
    p.show(Utterance(0, 2, "hello world", True))
    out = capsys.readouterr().out
    assert "… hel" in out
    assert out.endswith("[00:00.0 → 00:02.0] hello world\n")


def test_bad_model_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SCRIBELY_STT__MODEL", "gigantic")
    with pytest.raises(SystemExit) as exc:
        main(["--seconds", "1"])
    assert exc.value.code == 2
    assert "Unknown speech model" in capsys.readouterr().err
