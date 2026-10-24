"""app.py renders and keeps results across reruns. Mode A/B entry points are replaced with canned results: no network."""
import datetime
from pathlib import Path

import modes.request
import modes.scheduled
from streamlit.testing.v1 import AppTest

from schemas import Angle, Brief, DraftAttempt, RunResult, Violation

AD = ("CANNED DRAFT\n\nCommand starts at $99 a month.\n\n"
      "Start free https://command.hemut.com/signup?utm_source=trxckwrld&utm_medium=short_ad&utm_campaign=x")
BRIEF = Brief(origin="request", audience="a", pain="p", hemut_feature="f", format="short_ad", claim_ids=[])
RESULT = RunResult(run_id="x", run_dir="out/runs/x", status="ok", brief=BRIEF,
                   angles=[Angle(hook="hook", pain="p", feature="f", claim_ids=[])],
                   drafts=[[DraftAttempt(attempt=0, rendered_text=AD, violations=[])]])


def click(at, label):
    return next(b for b in at.button if b.label == label).click().run()


def drafts_shown(at):
    return sum("CANNED DRAFT" in m.value for m in at.markdown)


def test_app_runs_both_modes_and_keeps_results(monkeypatch):
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: RESULT)
    monkeypatch.setattr(modes.scheduled, "run_week", lambda day, plan, on_event: iter([RESULT]))
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert not at.exception and len(at.dataframe) == 2  # knowledge tab

    click(at, "Run")
    assert at.error and drafts_shown(at) == 0  # blank request is rejected by Request, not drafted
    at.text_area[0].input("Social post about detention").run()
    assert drafts_shown(click(at, "Run")) == 1
    assert drafts_shown(click(at, "Draft all")) == 2
    click(at, "Plan")  # a rerun must not wipe either tab's results
    assert drafts_shown(at) == 2 and any(m.value.startswith("**1. The office rebuilds the IFTA return") for m in at.markdown)


def test_app_shows_error_status(monkeypatch):
    def fail(request, on_event):
        raise RuntimeError("authentication_error")
    monkeypatch.setattr(modes.request, "run_request", fail)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.text_area[0].input("Social post about detention").run()
    click(at, "Run")
    assert not at.exception and any("Status: error" in e.value for e in at.error)
    assert any("authentication_error" in t.value for t in at.text)  # folded into Details


def test_new_week_date_drops_old_drafts(monkeypatch):
    monkeypatch.setattr(modes.scheduled, "run_week", lambda day, plan, on_event: iter([RESULT]))
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert drafts_shown(click(at, "Draft all")) == 1
    at.date_input[0].set_value(datetime.date(2026, 11, 7)).run()
    assert drafts_shown(click(at, "Plan")) == 0


def test_dollar_signs_are_not_latex(monkeypatch):
    gap = RunResult(run_id="x", run_dir="out/runs/x", status="needs_source", needs_source=["$50 off fuel", "$20 off Command"])
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: gap)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.text_area[0].input("Post about $50 off fuel and $20 off Command").run()
    click(at, "Run")
    assert any(r"\$50 off fuel" in w.value for w in at.warning)


def test_only_passing_ads_are_shown(monkeypatch):
    bad = [DraftAttempt(attempt=n, rendered_text=None, violations=[Violation(code="BANNED_WORD", message="banned: 'guaranteed'")])
           for n in range(3)]
    mixed = RESULT.model_copy(update={"angles": RESULT.angles * 2, "drafts": [bad, RESULT.drafts[0]]})
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: mixed)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.text_area[0].input("Social post about detention").run()
    click(at, "Run")
    shown = " ".join(m.value for m in at.markdown) + " ".join(t.value for t in at.text)
    assert drafts_shown(at) == 1 and "BANNED_WORD" not in shown and "guaranteed" not in shown
    assert any(r"\$99" in m.value for m in at.markdown) and any("Start free →" in m.value for m in at.markdown)
