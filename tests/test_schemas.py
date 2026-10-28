import datetime

import pytest
from pydantic import BaseModel, ValidationError

from schemas import (
    Angle, BridgeEntry, Brief, CallUsage, Claim, DraftAttempt, PlaceholderError, PlanItem, Request, RunResult,
    SeasonWindow, StatCard, TrxckwrldPost, Violation,
    render_post, used_claim_ids,
)

URL = "https://hemut.com/pricing?utm_source=trxckwrld&utm_medium=post&utm_campaign=ifta-q4"
BRIEF = {
    "origin": "request", "audience": "5-15 truck fleets", "audience_id": "fleet-owner", "pain": "IFTA quarters eat a weekend",
    "hemut_feature": "IFTA quarterly reports", "format": "reddit_post", "claim_ids": ["command-base-price"],
}
POST = {
    "title": "IFTA without the weekend", "body": "Command starts at {{claim:command-base-price}}.",
    "cta_text": "Start free", "cta_url": URL, "claim_ids_used": ["command-base-price"],
}
VALID: list[tuple[type[BaseModel], dict]] = [
    (Request, {"text": "Reddit-style ad about IFTA automation for 5-15 truck fleets"}),
    (Brief, BRIEF),
    (Angle, {"hook": "Your IFTA weekend", "pain": "manual mileage", "feature": "IFTA reports", "claim_ids": []}),
    (StatCard, {"claim_id": "command-base-price", "label": "Command starts at"}),
    (TrxckwrldPost, POST),
    (Violation, {"code": "BANNED_WORD", "message": "'guarantee' is banned", "span": "guaranteed"}),
    (DraftAttempt, {"attempt": 1, "raw_post": POST, "rendered_text": "...", "violations": []}),
    (RunResult, {"run_id": "r1", "run_dir": "out/runs/r1", "status": "needs_source", "needs_source": ["a deal"]}),
    (SeasonWindow, {
        "id": "ifta-q4", "name": "IFTA Q4 filing", "start": "01-01",
        "end": "01-31", "lead_days": 14, "source_url": "https://example.com/ifta", "checked": "2026-10-23",
    }),
    (BridgeEntry, {"tag": "ifta-q4", "pain": "quarterly IFTA return", "hemut_feature": "IFTA reports", "claim_ids": []}),
    (PlanItem, {"brief": BRIEF, "reason": "IFTA Q4 deadline Jan 31 is 12 days out"}),
    (CallUsage, {"step": "draft", "model": "claude-opus-5-5", "input_tokens": 120, "output_tokens": 900, "thinking_tokens": 600,
                 "duration_s": 12.5}),
]
IDS = [m.__name__ for m, _ in VALID]
DATA = dict(VALID)


@pytest.mark.parametrize("model,data", VALID, ids=IDS)
def test_valid(model, data):
    model.model_validate(data)


@pytest.mark.parametrize("model,data", VALID, ids=IDS)
def test_extra_key_rejected(model, data):
    with pytest.raises(ValidationError, match="surprise"):
        model.model_validate({**data, "surprise": 1})


@pytest.mark.parametrize("model,data,field,bad", [
    (Brief, BRIEF, "origin", "viral"),
    (Brief, BRIEF, "format", "tweet"),
    (Brief, BRIEF, "sensitivity", "medium"),
    (Violation, DATA[Violation], "code", "TYPO"),
    (RunResult, DATA[RunResult], "status", "done"),
])
def test_bad_literal_rejected(model, data, field, bad):
    with pytest.raises(ValidationError, match=field):
        model.model_validate({**data, field: bad})


@pytest.mark.parametrize("text", ["", "   \n"])
def test_blank_request_text_rejected(text):
    with pytest.raises(ValidationError):
        Request(text=text)


@pytest.mark.parametrize("url", [
    "https://hemut.com/pricing",
    "https://hemut.com/pricing?utm_source=trxckwrld&utm_medium=post",
    "https://hemut.com/pricing?utm_source=&utm_medium=post&utm_campaign=x",
    "hemut.com/pricing?utm_source=a&utm_medium=b&utm_campaign=c",
    "https://hemut.com/signup?utm_source=trxckwrld&utm_medium=post&utm_campaign=x",  # not one of the two CTA pages
    "https://command.hemut.co/signup?utm_source=trxckwrld&utm_medium=post&utm_campaign=x",
    "https://hemut.com/pricing?utm_source=reddit&utm_medium=post&utm_campaign=x",
])
def test_bad_utm_rejected(url):
    with pytest.raises(ValidationError, match="utm"):
        TrxckwrldPost.model_validate({**POST, "cta_url": url})


def test_season_window_may_wrap_past_year_end():
    w = SeasonWindow.model_validate({**DATA[SeasonWindow], "start": "12-15", "end": "01-31"})
    assert (w.start, w.end) == ("12-15", "01-31")


@pytest.mark.parametrize("field,bad", [("start", "02-30"), ("end", "13-01"), ("start", "1-05"), ("lead_days", -1)])
def test_bad_season_window_rejected(field, bad):
    with pytest.raises(ValidationError):
        SeasonWindow.model_validate({**DATA[SeasonWindow], field: bad})


# ---------------------------------------------------------------- placeholders

def claim(id, phrasings, type="price", value=99):
    return Claim(
        id=id, type=type, value=value, phrasings=phrasings, source_url="https://hemut.com/pricing",
        source_snapshot="knowledge/sources/pricing_2026-10-23.txt", checked=datetime.date(2026, 10, 23),
        requires_approval=False,
    )


CLAIMS = {
    "command-base-price": claim("command-base-price", ["$99 a month with 3 trucks included", "$99 a month"]),
    "trial-days": claim("trial-days", ["30 days or 5 loads per truck, whichever comes first"], value=30),
    "customer-quote": claim("customer-quote", [], type="company", value="A testimonial"),
}


def post(**overrides):
    return TrxckwrldPost.model_validate({**POST, **overrides})


def test_render_fills_first_and_nth_phrasing_and_stat_card():
    p = post(
        body="Command is {{claim:command-base-price:1}}. Full price: {{claim:command-base-price}}.",
        stat_card={"claim_id": "trial-days", "label": "Free trial"},
    )
    assert render_post(p, CLAIMS) == (
        "IFTA without the weekend\n\n"
        "Command is $99 a month. Full price: $99 a month with 3 trucks included.\n\n"
        "Free trial: 30 days or 5 loads per truck, whichever comes first\n\n"
        f"Start free {URL}"
    )
    assert used_claim_ids(p) == {"command-base-price", "trial-days"}


@pytest.mark.parametrize("body,match", [
    ("{{claim:no-such-claim}}", "unknown claim id"),
    ("{{claim:command-base-price:2}}", "only 2 phrasing"),
    ("{{claim:customer-quote}}", "no phrasings"),
    ("{{claim:Bad_Id}}", "malformed"),
    ("Only {{price}} a month", "malformed"),
])
def test_render_bad_placeholder_raises(body, match):
    with pytest.raises(PlaceholderError, match=match):
        render_post(post(body=body), CLAIMS)


def test_render_bad_stat_card_claim_raises():
    with pytest.raises(PlaceholderError, match="unknown claim id"):
        render_post(post(stat_card={"claim_id": "no-such-claim", "label": "Save"}), CLAIMS)


def test_run_result_error_status():
    assert RunResult(run_id="r1", run_dir="out/runs/r1", status="error").status == "error"


def test_call_usage_needs_duration():
    data = {k: v for k, v in VALID[-1][1].items() if k != "duration_s"}
    with pytest.raises(ValidationError, match="duration_s"):
        CallUsage.model_validate(data)
