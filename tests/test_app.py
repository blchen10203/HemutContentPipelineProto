"""app.py renders and keeps results across reruns. Mode A/B entry points are replaced with canned results: no network."""
import datetime
from pathlib import Path

import knowledge.add_feature
import modes.request
import modes.scheduled
from streamlit.testing.v1 import AppTest

from schemas import AdImage, Angle, Brief, CallUsage, DraftAttempt, RunResult, Violation

AD = ("CANNED DRAFT\n\nCommand starts at $99 a month.\n\n"
      "Start free https://command.hemut.com/signup?utm_source=trxckwrld&utm_medium=short_ad&utm_campaign=x")
IFTA_WEEK = datetime.date(2026, 10, 12)  # fixed, never today: the week's plan leads with IFTA Q3 here
BRIEF = Brief(origin="request", audience="a", audience_id="fleet-owner", pain="p", hemut_feature="f", format="short_ad", claim_ids=[])
RESULT = RunResult(run_id="x", run_dir="out/runs/x", status="ok", brief=BRIEF,
                   angles=[Angle(hook="hook", pain="p", feature="f", claim_ids=[])],
                   drafts=[[DraftAttempt(attempt=0, rendered_text=AD, violations=[])]],
                   usage=[CallUsage(step="draft", model="claude-opus-5-5", input_tokens=1000, output_tokens=5000,
                                    thinking_tokens=4000, cache_read_input_tokens=6700, duration_s=20.0)])  # $0.10534


def usage_captions(at):
    return [c.value for c in at.caption if c.value.startswith("API use:")]


def click(at, label):
    return next(b for b in at.button if b.label == label).click().run()


def drafts_shown(at):
    return sum("CANNED DRAFT" in m.value for m in at.markdown)


def test_app_runs_both_modes_and_keeps_results(monkeypatch):
    monkeypatch.setenv("SHOW_API_USE", "0")  # set, not deleted: the app's load_dotenv() would refill a missing one from .env
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: RESULT)
    monkeypatch.setattr(modes.scheduled, "run_week", lambda day, plan, on_event: iter([RESULT]))
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.date_input[0].set_value(IFTA_WEEK).run()
    assert not at.exception and len(at.dataframe) == 3  # knowledge tab

    click(at, "Run")
    assert at.error and drafts_shown(at) == 0  # blank request is rejected by Request, not drafted
    at.text_area[0].input("Social post about detention").run()
    assert drafts_shown(click(at, "Run")) == 1
    assert drafts_shown(click(at, "Draft all")) == 2
    assert usage_captions(at) == []  # cost stays off screen unless SHOW_API_USE=1
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


def test_finished_ad_shows_its_image(monkeypatch, pool):
    bad = [DraftAttempt(attempt=0, rendered_text=None, violations=[Violation(code="BANNED_WORD", message="x")])]
    mixed = RESULT.model_copy(update={"angles": RESULT.angles * 2, "drafts": [bad, RESULT.drafts[0]],
                                      "images": [None, AdImage(path=str(pool / "01b-overview-kpi-cards-closeup.png"), caption="Cards at a glance.")]})  # picked when drafting
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: mixed)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert not at.get("image")
    at.text_area[0].input("Social post about detention").run()
    click(at, "Run")
    assert len(at.get("image")) == 1  # the finished ad only, not the failed one
    assert at.get("image")[0].proto.imgs[0].caption == "Cards at a glance."
    assert len(click(at, "Plan").get("image")) == 1  # a rerun shows the same ad with its image


def test_api_use_caption_only_with_flag(monkeypatch):
    monkeypatch.setenv("SHOW_API_USE", "1")
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: RESULT)
    monkeypatch.setattr(modes.scheduled, "run_week", lambda day, plan, on_event: iter([RESULT]))
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.text_area[0].input("Social post about detention").run()
    click(at, "Run")
    assert usage_captions(at) == [r"API use: 1 calls · 7,700 input tokens (6,700 from cache) · 5,000 output (4,000 thinking) · ≈ \$0.11"]
    click(at, "Draft all")
    assert len(usage_captions(at)) == 2  # one under the request, one under the week


def emit_intermediate(on_event):
    """Every progress event run_brief sends, carrying text that must never reach the screen."""
    on_event("brief", {"format": "social_post", "audience": "HIDDEN-AUDIENCE", "pain": "HIDDEN-PAIN", "hemut_feature": "HIDDEN-FEATURE"})
    on_event("angles", {"angles": [{"hook": "HIDDEN-HOOK", "pain": "p", "feature": "f", "claim_ids": []}]})
    on_event("draft", {"angle": 0, "attempt": 0, "violations": [{"code": "BANNED_WORD", "message": "HIDDEN-VIOLATION"}]})
    on_event("draft", {"angle": 0, "attempt": 1, "violations": []})
    on_event("done", {"status": "ok", "run_dir": "HIDDEN-RUN-DIR"})


def screen_text(at):
    elements = [*at.markdown, *at.caption, *at.text, *at.subheader, *at.info, *at.warning, *at.error]
    return " ".join(e.value for e in elements) + " ".join(s.label for s in at.status)


def test_only_final_drafts_shown_while_and_after_running(monkeypatch):
    def run_request(request, on_event):
        emit_intermediate(on_event)
        return RESULT

    def run_week(day, plan, on_event):
        emit_intermediate(on_event)
        yield RESULT

    monkeypatch.setattr(modes.request, "run_request", run_request)
    monkeypatch.setattr(modes.scheduled, "run_week", run_week)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.date_input[0].set_value(IFTA_WEEK).run()
    at.text_area[0].input("Social post about detention").run()
    click(at, "Run")
    assert drafts_shown(at) == 1 and "HIDDEN" not in screen_text(at)
    assert [s.label for s in at.status] == ["Drafting: done"]
    click(at, "Draft all")
    assert drafts_shown(at) == 2 and "HIDDEN" not in screen_text(at)
    assert any(m.value.startswith("**1. The office rebuilds the IFTA return") for m in at.markdown)  # the week's topic list stays


def test_feature_dropdown_reaches_the_request(monkeypatch):
    seen = []
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: seen.append(request) or RESULT)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    box = at.selectbox[0]
    assert box.options[0] == "Any (from the text)" and "Dispatch board with hours of service" in box.options
    box.select("Dispatch board with hours of service").run()
    at.text_area[0].input("Short ad for dispatchers").run()
    click(at, "Run")
    assert seen[-1].feature_id == "dispatch-board-hos"
    at.selectbox[0].select("Any (from the text)").run()
    click(at, "Run")
    assert seen[-1].feature_id is None


def fill_feature_form(at):
    at.text_input(key="nf_name").input("Voice agents for check calls")
    at.text_input(key="nf_does").input("Places driver check calls automatically")
    at.text_input(key="nf_url").input("https://hemut.com/hemi")
    at.text_input(key="nf_w1").input("Hemi places the driver check calls for you")
    at.text_input(key="nf_verified").input("Jane Doe (Product Lead)")
    at.text_input(key="nf_pain").input("Dispatchers lose hours chasing drivers for check calls.")
    at.multiselect(key="nf_aud").select(at.multiselect(key="nf_aud").options[0])
    return click(at, "Add feature")


def test_add_feature_form_calls_add_feature(monkeypatch):
    got = []
    monkeypatch.setattr(knowledge.add_feature, "add_feature", lambda f, **k: got.append(f) or (f.id, [Path("knowledge/sources/x_2026-11-06.txt")]))
    at = fill_feature_form(AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run())
    assert got[0].wordings == ["Hemi places the driver check calls for you"] and got[0].caption is None
    assert any("Live:" in s.value and "`knowledge/sources/x_2026-11-06.txt`" in s.value for s in at.success)


def test_add_feature_error_shows_message(monkeypatch):
    def fail(f, **k): raise ValueError("url: could not fetch the page")
    monkeypatch.setattr(knowledge.add_feature, "add_feature", fail)
    at = fill_feature_form(AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run())
    assert any("could not fetch" in e.value for e in at.error) and not at.exception
