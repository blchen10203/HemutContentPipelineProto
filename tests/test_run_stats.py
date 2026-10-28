"""scripts/run_stats.py on hand-made meta.json files. No network."""
import json

from scripts.run_stats import call_steps, load, pass_attempt, report


def attempt(n, *codes):
    return {"attempt": n, "violations": [{"code": c, "message": c} for c in codes]}


def call(step, secs, out):
    return {"step": step, "duration_s": secs, "output_tokens": out}


# Angle 1 passes first time; angle 2 fails once with UNBACKED_NUMBER, then passes. Draft calls are logged in angle order.
META = {
    "mode": "A", "status": "ok", "duration_s": 40.0,
    "validator": [[attempt(0)], [attempt(0, "UNBACKED_NUMBER", "BANNED_WORD"), attempt(1)]],
    "usage": {"calls": [call("normalize", 4, 100), call("angles", 6, 200), call("draft", 15, 1000), call("draft", 14, 900),
                        call("draft", 10, 800)],
              "total": {"calls": 5, "usd_estimate": 0.3}},
}


def test_draft_calls_split_into_first_attempts_and_retries():
    assert call_steps(META) == ["normalize", "angles", "draft-first-attempt", "draft-first-attempt", "draft-retry"]


def test_pass_attempt():
    assert [pass_attempt(d) for d in META["validator"]] == ["1", "2"]
    assert pass_attempt([attempt(0, "X"), attempt(1, "X"), attempt(2, "X")]) == "never"


def test_report_totals_and_old_runs(tmp_path):
    (tmp_path / "new").mkdir()
    (tmp_path / "new" / "meta.json").write_text(json.dumps(META), encoding="utf-8")
    (tmp_path / "old").mkdir()  # before duration_s and usage existed
    (tmp_path / "old" / "meta.json").write_text(json.dumps({"mode": "B", "status": "ok", "validator": [[attempt(0)]]}), encoding="utf-8")
    text = report(load([tmp_path / "new", tmp_path / "old"]))
    assert "Runs: 2  timed: 1  drafts: 3" in text
    assert "Average attempts per draft: 1.33" in text
    assert "Drafts passing on attempt: 1 67% (2)  2 33% (1)  3 0% (0)  never 0% (0)" in text
    assert "First-attempt violations by code: UNBACKED_NUMBER 1, BANNED_WORD 1" in text
    assert "normalize 10%  angles 15%  drafts (overlapping) 75%" in text  # wall: 4 + 6 serial, the other 30 s drafting
    assert "draft-retry 20%" in text  # 10 of 49 API seconds
