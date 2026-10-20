import json

from chatreader import selfcheck
from chatreader.__main__ import run


def ok(detail="fine"):
    return lambda app: detail


def boom(app):
    raise RuntimeError("broken")


def test_all_steps_ok_exits_0(tmp_path):
    code, result = selfcheck.run_check(tmp_path, steps={"a": ok(), "b": ok("x")})
    assert code == 0 and result["ok"] is True and result["steps"] == {"a": "ok: fine", "b": "ok: x"}


def test_one_failing_step_exits_1_and_names_it(tmp_path):
    code, result = selfcheck.run_check(tmp_path, steps={"a": ok(), "b": boom, "c": ok()})
    assert code == 1 and result["ok"] is False
    assert result["steps"]["b"].startswith("failed: RuntimeError: broken") and "c" in result["steps"]


def test_missing_model_skips_synth_and_still_ok(tmp_path):
    assert selfcheck.synth_step(tmp_path).startswith("skipped")
    code, result = selfcheck.run_check(tmp_path, steps={"synth": selfcheck.synth_step})
    assert code == 0 and result["steps"]["synth"].startswith("ok: skipped")


def test_output_is_single_json_line(tmp_path, capsys):
    assert selfcheck.main_check(tmp_path, steps={"a": ok()}) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and set(json.loads(lines[0])) == {"ok", "steps"}


def test_check_flag_dispatches(tmp_path):
    calls = []
    code = run(["--check", "--home", str(tmp_path)], acquire=lambda: calls.append("acquire"),
               start=lambda h: calls.append("start"), check=lambda app: calls.append(("check", app)) or 0)
    assert code == 0 and calls == [("check", tmp_path)]


def test_real_steps_pass(tmp_path):
    for name in ("imports", "language", "server"):
        assert selfcheck.DEFAULT_STEPS[name](tmp_path)


def test_check_survives_missing_streams_and_writes_result_file(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    assert run(["--check", "--home", str(tmp_path)]) in (0, 1)
    data = json.loads((tmp_path / "check-result.json").read_text("utf-8"))
    assert data["steps"]["server"].startswith("ok"), data


def test_check_creates_a_missing_home_folder(tmp_path):
    home = tmp_path / "new" / "home"
    assert selfcheck.main_check(home, steps={"a": ok()}) == 0
    assert (home / "check-result.json").exists()
