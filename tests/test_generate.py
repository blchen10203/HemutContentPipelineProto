"""run_brief() with a scripted fake client: retry loop, statuses, events and run files. No network."""
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

import pytest

from generate import N_ANGLES, Refused, run_brief
from schemas import Brief

GOLDEN = Path(__file__).parent / "golden"
GOOD = json.dumps(yaml.safe_load((GOLDEN / "good" / "reddit_ifta.yaml").read_text(encoding="utf-8"))["post"])
BAD = json.dumps(yaml.safe_load((GOLDEN / "bad" / "banned_guaranteed.yaml").read_text(encoding="utf-8"))["post"])
ANGLES = json.dumps({"angles": [
    {"hook": f"hook {i}", "pain": "IFTA by hand", "feature": "IFTA from loads", "claim_ids": ["hemi-desk-settlements-ifta"]}
    for i in range(N_ANGLES)
]})
BRIEF = Brief(origin="request", audience="small fleets", pain="IFTA by hand", hemut_feature="IFTA",
              format="reddit_post", claim_ids=["hemi-desk-settlements-ifta"])


class FakeClient:
    def __init__(self, *replies, stop_reason="end_turn"):
        self.replies, self.calls, self.stop_reason = list(replies), [], stop_reason
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=reply)])


def run(client, tmp_path, brief=BRIEF):
    events = []
    result = run_brief(brief, client=client, out_root=tmp_path, on_event=lambda name, payload: events.append(name))
    return result, events


def test_good_first_try(tmp_path):
    client = FakeClient(ANGLES, GOOD)
    result, events = run(client, tmp_path)
    assert result.status == "ok"
    assert [len(d) for d in result.drafts] == [1] * N_ANGLES
    assert "IFTA" in result.drafts[0][0].rendered_text and "{{" not in result.drafts[0][0].rendered_text
    assert events == ["angles"] + ["draft"] * N_ANGLES + ["done"]
    assert len(client.calls) == 1 + N_ANGLES
    meta = json.loads((Path(result.run_dir) / "meta.json").read_text(encoding="utf-8"))
    assert meta["mode"] == "A" and meta["brief_origin"] == "request" and set(meta["prompt_versions"]) == {"system.txt", "angles.txt", "draft.txt", "normalize.txt"}
    assert (Path(result.run_dir) / "draft-1.md").is_file()
    system = client.calls[0]["system"][0]["text"]
    assert "command-base-price" in system and "{fact_sheet}" not in system and "{{claim:<id>}}" in system


def test_retry_sends_violations_then_passes(tmp_path):
    client = FakeClient(ANGLES, BAD, GOOD)
    result, _ = run(client, tmp_path)
    first = result.drafts[0]
    assert [a.attempt for a in first] == [0, 1] and first[0].violations and not first[1].violations
    retry = client.calls[2]["messages"]
    assert retry[1]["role"] == "assistant" and "BANNED_WORD" in retry[2]["content"]
    assert result.status == "ok"


def test_gives_up_after_two_retries(tmp_path):
    result, _ = run(FakeClient(ANGLES, BAD), tmp_path)
    assert result.status == "failed_validation"
    assert [len(d) for d in result.drafts] == [3] * N_ANGLES
    assert "Failed validation" in (Path(result.run_dir) / "draft-1.md").read_text(encoding="utf-8")


def test_not_json_is_a_parse_error(tmp_path):
    result, _ = run(FakeClient(ANGLES, "not json", GOOD), tmp_path)
    assert result.drafts[0][0].violations[0].code == "PARSE_ERROR" and result.status == "ok"


def test_approval_flag_is_derived_not_trusted(tmp_path):
    good = yaml.safe_load((GOLDEN / "good" / "approval_tracking_link.yaml").read_text(encoding="utf-8"))["post"]
    good["requires_approval"] = False  # the model got it wrong; the pipeline sets it from the claims
    result, _ = run(FakeClient(ANGLES, json.dumps(good)), tmp_path)
    assert result.status == "ok" and result.drafts[0][0].raw_post.requires_approval is True


def test_needs_source_and_sensitive_make_no_calls(tmp_path):
    for brief, status in [
        (BRIEF.model_copy(update={"needs_source": ["a 40% fuel discount"]}), "needs_source"),
        (BRIEF.model_copy(update={"sensitivity": "high"}), "blocked_sensitive"),
    ]:
        client = FakeClient(ANGLES)
        result, events = run(client, tmp_path, brief)
        assert result.status == status and client.calls == [] and events == ["done"]
        assert (Path(result.run_dir) / "meta.json").is_file()


def run_dirs(tmp_path):
    return [d for d in tmp_path.iterdir() if d.is_dir()]


def test_api_error_still_writes_run_folder(tmp_path):
    with pytest.raises(RuntimeError, match="boom") as info:
        run(FakeClient(ANGLES, BAD, GOOD, RuntimeError("boom")), tmp_path)  # fails on the second angle's first call
    (run_dir,) = run_dirs(tmp_path)
    assert str(run_dir) in info.value.__notes__[0]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "error" and "RuntimeError: boom" in meta["error"]
    assert [len(d) for d in meta["validator"]] == [2, 0]  # angle 1's two attempts kept, angle 2 had none
    assert (run_dir / "draft-1.md").is_file() and not (run_dir / "draft-2.md").exists()


def test_refused_angles_call_writes_run_folder_and_raises(tmp_path):
    with pytest.raises(Refused):
        run(FakeClient(ANGLES, stop_reason="refusal"), tmp_path)
    (run_dir,) = run_dirs(tmp_path)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "error" and "refusal" in meta["error"] and meta["validator"] == []
