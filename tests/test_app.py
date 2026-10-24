"""app.py renders and keeps results across reruns. Mode A/B entry points are replaced with canned results: no network."""
from pathlib import Path

import modes.request
import modes.scheduled
from streamlit.testing.v1 import AppTest

from schemas import Angle, Brief, DraftAttempt, RunResult

BRIEF = Brief(origin="request", audience="a", pain="p", hemut_feature="f", format="short_ad", claim_ids=[])
RESULT = RunResult(run_id="x", run_dir="out/runs/x", status="ok", brief=BRIEF,
                   angles=[Angle(hook="hook", pain="p", feature="f", claim_ids=[])],
                   drafts=[[DraftAttempt(attempt=0, rendered_text="CANNED DRAFT", violations=[])]])


def click(at, label):
    return next(b for b in at.button if b.label == label).click().run()


def drafts_shown(at):
    return sum("CANNED DRAFT" in t.value for t in at.text)


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
    assert drafts_shown(at) == 2 and any(m.value.startswith("**1. ifta-q3**") for m in at.markdown)
