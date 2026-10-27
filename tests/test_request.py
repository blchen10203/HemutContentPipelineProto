"""Mode A with a scripted fake client: request -> Brief, gap rule, sensitivity. No network."""
import json

import pytest

from test_generate import ANGLES, GOOD, N_ANGLES, FakeClient

from knowledge.loader import load_claims
from modes.request import request_to_brief, run_request
from schemas import Request

CLAIMS = load_claims()


def brief_reply(**overrides) -> str:
    brief = {"origin": "trend", "audience": "5-15 truck fleets", "audience_id": "fleet-owner", "pain": "IFTA by hand", "hemut_feature": "IFTA from loads",
             "format": "reddit_post", "claim_ids": ["hemi-desk-settlements-ifta", "command-base-price"],
             "needs_source": [], "sensitivity": "low", "origin_ref": "made up"}
    return json.dumps(brief | overrides)


def test_covered_request_gives_brief_with_real_claim_ids():
    client = FakeClient(brief_reply())
    brief = request_to_brief(Request(text="Reddit-style post about IFTA automation for 5-15 truck fleets"), CLAIMS, client=client)
    assert brief.origin == "request" and brief.origin_ref is None  # forced, whatever the model said
    assert brief.claim_ids == ["hemi-desk-settlements-ifta", "command-base-price"] and brief.needs_source == []
    prompt = client.calls[0]["messages"][0]["content"]
    assert "IFTA automation" in prompt and "{request}" not in prompt


def test_made_up_claim_id_is_a_gap():
    client = FakeClient(brief_reply(claim_ids=["hemi-desk-settlements-ifta", "fuel-card"]))
    brief = request_to_brief(Request(text="Post about the fuel card"), CLAIMS, client=client)
    assert brief.claim_ids == ["hemi-desk-settlements-ifta"] and brief.needs_source == ["no claim with id 'fuel-card'"]


def test_uncovered_request_needs_source_and_makes_no_draft_calls(tmp_path):
    gaps = ["Hemut's new fuel card", "50% off in November"]
    client = FakeClient(brief_reply(needs_source=gaps), ANGLES, GOOD)
    result = run_request(Request(text="Ad for Hemut's new fuel card, 50% off in November"), client=client, out_root=tmp_path)
    assert result.status == "needs_source" and result.needs_source == gaps
    assert len(client.calls) == 1 and result.drafts == []


def test_attached_source_does_not_cover_gaps_yet(tmp_path):
    client = FakeClient(brief_reply(needs_source=["50% off in November"]))
    request = Request(text="Ad for 50% off in November", sources=[{"kind": "text", "value": "Promo: 50% off in November"}])
    result = run_request(request, client=client, out_root=tmp_path)
    assert result.status == "needs_source" and "Promo" not in client.calls[0]["messages"][0]["content"]


def test_sensitive_request_is_blocked(tmp_path):
    client = FakeClient(brief_reply(sensitivity="high"), ANGLES, GOOD)
    result = run_request(Request(text="Post about the I-80 pileup"), client=client, out_root=tmp_path)
    assert result.status == "blocked_sensitive" and len(client.calls) == 1


def test_covered_request_runs_the_core(tmp_path):
    client = FakeClient(brief_reply(), ANGLES, GOOD)
    result = run_request(Request(text="Reddit-style post about IFTA automation"), client=client, out_root=tmp_path)
    assert result.status == "ok" and len(client.calls) == 2 + N_ANGLES
    assert client.calls[0]["system"] == client.calls[1]["system"]  # normalize shares the cached system prompt


def test_failed_request_call_still_writes_run_folder(tmp_path):
    with pytest.raises(RuntimeError, match="overloaded") as info:
        run_request(Request(text="Reddit-style post about IFTA"), client=FakeClient(RuntimeError("overloaded")), out_root=tmp_path)
    (run_dir,) = [d for d in tmp_path.iterdir() if d.is_dir()]
    assert str(run_dir) in info.value.__notes__[0]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "error" and meta["mode"] == "A" and "RuntimeError: overloaded" in meta["error"]
    assert json.loads((run_dir / "result.json").read_text(encoding="utf-8"))["status"] == "error"
    assert "normalize.txt" in meta["prompt_versions"] and meta["validator"] == []


def test_interrupted_request_call_still_writes_run_folder(tmp_path):
    # a Streamlit rerun during the request -> Brief call is a BaseException, like KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_request(Request(text="Reddit-style post about IFTA"), client=FakeClient(KeyboardInterrupt()), out_root=tmp_path)
    (run_dir,) = [d for d in tmp_path.iterdir() if d.is_dir()]
    assert json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))["status"] == "error"


def test_request_maps_to_a_real_persona_id():
    client = FakeClient(brief_reply())
    brief = request_to_brief(Request(text="Reddit-style post about IFTA automation for 5-15 truck fleets"), CLAIMS, client=client)
    assert brief.audience == "5-15 truck fleets" and brief.audience_id == "fleet-owner"  # requester's words kept
    call = client.calls[0]
    assert "- fleet-owner: Owner running a small fleet." in call["messages"][0]["content"]
    schema = call["output_config"]["format"]["schema"]
    assert set(schema["properties"]["audience_id"]["enum"]) == {"fleet-owner", "dispatcher", "back-office", "carrier-exec"}
