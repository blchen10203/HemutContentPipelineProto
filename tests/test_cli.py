"""cli.py reports API/auth failures as status: error instead of a traceback. No network."""
import pytest

import cli


def test_api_error_prints_error_status(monkeypatch, capsys):
    def fail(request, on_event):
        e = RuntimeError("authentication_error")
        e.add_note("run folder: out/runs/x")
        raise e
    monkeypatch.setattr(cli, "run_request", fail)
    with pytest.raises(SystemExit) as info:
        cli.main(["request", "IFTA post"])
    out = capsys.readouterr().out
    assert info.value.code == 1 and "status: error" in out and "authentication_error" in out and "out/runs/x" in out
