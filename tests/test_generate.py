"""run_brief() with a scripted fake client: retry loop, statuses, events and run files. No network."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import yaml

import pytest

import generate
from generate import N_ANGLES, Refused, run_brief, usage_total
from schemas import Brief, CallUsage

GOLDEN = Path(__file__).parent / "golden"


def golden(kind: str, name: str) -> str:
    return json.dumps(yaml.safe_load((GOLDEN / kind / f"{name}.yaml").read_text(encoding="utf-8"))["post"])


GOOD = golden("good", "reddit_ifta")
BAD = golden("bad", "banned_guaranteed")
ANGLES = json.dumps({"angles": [
    {"hook": f"hook {i}", "pain": "IFTA by hand", "feature": "IFTA from loads", "claim_ids": ["hemi-desk-settlements-ifta"]}
    for i in range(N_ANGLES)
]})
BRIEF = Brief(origin="request", audience="small fleets", audience_id="back-office", pain="IFTA by hand", hemut_feature="IFTA",
              format="reddit_post", claim_ids=["hemi-desk-settlements-ifta"])


# Every fake call: 100 uncached input, 6,700 read from cache, 500 output of which 300 thinking.
USAGE = SimpleNamespace(input_tokens=100, output_tokens=500, cache_read_input_tokens=6700, cache_creation_input_tokens=0,
                        output_tokens_details=SimpleNamespace(thinking_tokens=300))


class FakeClient:
    """Replies in call order (the last one repeats). Drafts run in parallel, so tests that need a reply for a given
    angle set DRAFT_WORKERS = 1 or use AngleClient."""
    def __init__(self, *replies, stop_reason="end_turn"):
        self.replies, self.calls, self.stop_reason = list(replies), [], stop_reason
        self.lock = threading.Lock()
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        with self.lock:
            self.calls.append(kwargs)
            reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, BaseException):
            raise reply
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=reply)],
                               model="claude-opus-5-5", usage=USAGE)


class AngleClient:
    """Thread-safe fake for parallel drafts. The angles call gets ANGLES; a draft call gets script[angle][attempt], with the
    angle read from its prompt (the angle's hook) and the attempt from the message count. before(angle, attempt) runs
    first, so a test can hold a call back. Draft calls report input_tokens 200 + angle, so usage order is visible."""
    def __init__(self, script, before=lambda angle, attempt: None):
        self.script, self.before, self.calls, self.lock = script, before, [], threading.Lock()
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        messages = kwargs["messages"]
        angle = next((i for i in range(N_ANGLES) if f'"hook": "hook {i}"' in messages[0]["content"]), None)
        attempt = (len(messages) - 1) // 2
        with self.lock:
            self.calls.append((angle, attempt))
        if angle is None:
            reply, input_tokens = ANGLES, 100
        else:
            self.before(angle, attempt)
            reply, input_tokens = self.script[angle][attempt], 200 + angle
        if isinstance(reply, BaseException):
            raise reply
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=reply)],
                               model="claude-opus-5-5", usage=SimpleNamespace(**{**vars(USAGE), "input_tokens": input_tokens}))


@pytest.fixture
def serial(monkeypatch):
    monkeypatch.setattr(generate, "DRAFT_WORKERS", 1)  # for tests that script FakeClient replies in call order


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
    assert events == ["brief", "angles"] + ["draft"] * N_ANGLES + ["done"]
    assert len(client.calls) == 1 + N_ANGLES
    meta = json.loads((Path(result.run_dir) / "meta.json").read_text(encoding="utf-8"))
    assert isinstance(meta["duration_s"], float) and meta["duration_s"] >= 0
    assert meta["mode"] == "A" and meta["brief_origin"] == "request" and set(meta["prompt_versions"]) == {"system.txt", "angles.txt", "draft.txt", "normalize.txt"}
    assert (Path(result.run_dir) / "draft-1.md").is_file()
    system = client.calls[0]["system"][0]["text"]
    assert "command-base-price" in system and "{fact_sheet}" not in system and "{{claim:<id>}}" in system


def test_retry_sends_violations_then_passes(tmp_path, serial):
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


def test_not_json_is_a_parse_error(tmp_path, serial):
    result, _ = run(FakeClient(ANGLES, "not json", GOOD), tmp_path)
    assert result.drafts[0][0].violations[0].code == "PARSE_ERROR" and result.status == "ok"


def test_approval_flag_is_derived_not_trusted(tmp_path):
    good = yaml.safe_load((GOLDEN / "good" / "tracking_link.yaml").read_text(encoding="utf-8"))["post"]
    good["requires_approval"] = True  # the model got it wrong; the pipeline sets it from the claims
    result, _ = run(FakeClient(ANGLES, json.dumps(good)), tmp_path)
    assert result.status == "ok" and result.drafts[0][0].raw_post.requires_approval is False


def test_needs_source_and_sensitive_make_no_calls(tmp_path):
    for brief, status in [
        (BRIEF.model_copy(update={"needs_source": ["a 40% fuel discount"]}), "needs_source"),
        (BRIEF.model_copy(update={"sensitivity": "high"}), "blocked_sensitive"),
    ]:
        client = FakeClient(ANGLES)
        result, events = run(client, tmp_path, brief)
        assert result.status == status and client.calls == [] and events == ["brief", "done"]
        assert (Path(result.run_dir) / "meta.json").is_file()


def run_dirs(tmp_path):
    return [d for d in tmp_path.iterdir() if d.is_dir()]


def test_api_error_still_writes_run_folder(tmp_path, serial):
    with pytest.raises(RuntimeError, match="boom") as info:
        run(FakeClient(ANGLES, BAD, GOOD, RuntimeError("boom")), tmp_path)  # fails on the second angle's first call
    (run_dir,) = run_dirs(tmp_path)
    assert str(run_dir) in info.value.__notes__[0]
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "error" and "RuntimeError: boom" in meta["error"]
    assert json.loads((run_dir / "result.json").read_text(encoding="utf-8"))["status"] == "error"
    assert [len(d) for d in meta["validator"]] == [2, 0, 0]  # angle 1's two attempts kept, angles 2 and 3 had none
    assert (run_dir / "draft-1.md").is_file() and not (run_dir / "draft-2.md").exists()


def test_refused_angles_call_writes_run_folder_and_raises(tmp_path):
    with pytest.raises(Refused):
        run(FakeClient(ANGLES, stop_reason="refusal"), tmp_path)
    (run_dir,) = run_dirs(tmp_path)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "error" and "refusal" in meta["error"] and meta["validator"] == []
    assert [c["step"] for c in meta["usage"]["calls"]] == ["angles"]  # a refused call is still billed, so still logged


def test_interrupt_mid_run_still_writes_meta(tmp_path, serial):
    # Streamlit's rerun exception is a BaseException like KeyboardInterrupt, not an Exception
    with pytest.raises(KeyboardInterrupt):
        run(FakeClient(ANGLES, GOOD, KeyboardInterrupt()), tmp_path)
    (run_dir,) = run_dirs(tmp_path)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "error" and "KeyboardInterrupt" in meta["error"]
    assert [len(d) for d in meta["validator"]] == [1, 0, 0]


def test_persona_block_reaches_angles_and_draft_prompts(tmp_path):
    client = FakeClient(ANGLES, GOOD)
    run(client, tmp_path)
    prompts = [c["messages"][0]["content"] for c in client.calls]  # angles call, then one draft call per angle
    for prompt in prompts:
        assert "Back-office and billing lead: Handles invoicing" in prompt and "Hesitates because of:" in prompt
        assert "{persona}" not in prompt
    assert "Back-office" not in client.calls[0]["system"][0]["text"]  # persona stays out of the cached system prompt


def test_unknown_persona_is_an_error_run(tmp_path):
    with pytest.raises(ValueError, match="audience_id 'nobody'"):
        run(FakeClient(ANGLES, GOOD), tmp_path, brief=BRIEF.model_copy(update={"audience_id": "nobody"}))
    (run_dir,) = tmp_path.iterdir()
    assert json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))["status"] == "error"


def test_usage_logged_per_call_with_total_and_cost(tmp_path):
    result, _ = run(FakeClient(ANGLES, GOOD), tmp_path)
    usage = json.loads((Path(result.run_dir) / "meta.json").read_text(encoding="utf-8"))["usage"]
    assert [c["step"] for c in usage["calls"]] == ["angles"] + ["draft"] * N_ANGLES
    seconds = [c.pop("duration_s") for c in usage["calls"]]
    assert all(isinstance(s, float) and s >= 0 for s in seconds)
    assert usage["calls"][0] == {"step": "angles", "model": "claude-opus-5-5", "input_tokens": 100, "output_tokens": 500,
                                 "thinking_tokens": 300, "cache_read_input_tokens": 6700, "cache_creation_input_tokens": 0}
    n = 1 + N_ANGLES
    # per call: (100 x $4 + 500 x $20 + 6,700 x $0.20) / 1M = $0.01174
    assert usage["total"] == {"calls": n, "input_tokens": 100 * n, "output_tokens": 500 * n, "thinking_tokens": 300 * n,
                              "cache_read_input_tokens": 6700 * n, "cache_creation_input_tokens": 0,
                              "usd_estimate": round(0.01174 * n, 4), "call_seconds": round(sum(seconds), 3)}
    assert result.usage[0].step == "angles"  # the UI reads it from the result, not from the file


def test_unpriced_model_and_unreported_thinking_stay_unknown():
    reported = CallUsage(step="angles", model="claude-opus-5-5", input_tokens=1, output_tokens=5, thinking_tokens=3, duration_s=2.0)
    unreported = CallUsage(step="draft", model="some-other-model", input_tokens=1, output_tokens=1, duration_s=3.5)  # thinking_tokens None
    total = usage_total([reported, unreported])
    assert total["usd_estimate"] is None and total["thinking_tokens"] is None  # unknown, never summed as zero
    assert usage_total([reported])["thinking_tokens"] == 3
    assert total["call_seconds"] == 5.5  # summed over calls, so more than the wall time once drafts overlap


# Parallel drafts: one good post per angle, each with its own title, so a draft found under the wrong angle shows.
POSTS = [golden("good", n) for n in ("reddit_ifta", "tracking_link", "mcleod_integration")]
TITLES = [json.loads(p)["title"] for p in POSTS]


def test_parallel_drafts_line_up_with_their_angles(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "DRAFT_WORKERS", 3)
    barrier = threading.Barrier(N_ANGLES, timeout=5)  # every first attempt waits for the others: proves they overlap

    def before(angle, attempt):
        if attempt == 0:
            barrier.wait()

    client = AngleClient([[POSTS[0]], [BAD, POSTS[1]], [POSTS[2]]], before)  # only angle 2 needs a retry
    events = []
    result = run_brief(BRIEF, client=client, out_root=tmp_path,
                       on_event=lambda name, payload: events.append((name, payload.get("angle"), threading.get_ident())))
    assert result.status == "ok"
    assert [len(d) for d in result.drafts] == [1, 2, 1]
    assert [d[-1].raw_post.title for d in result.drafts] == TITLES
    assert result.drafts[1][0].violations[0].code == "BANNED_WORD" and not result.drafts[1][1].violations
    assert {t for _, _, t in events} == {threading.get_ident()}  # on_event only ever runs on the caller's thread
    assert sorted(a for name, a, _ in events if name == "draft") == [0, 1, 1, 2]
    assert [c.input_tokens for c in result.usage] == [100, 200, 201, 201, 202]  # angles call, then angle order
    meta = json.loads((Path(result.run_dir) / "meta.json").read_text(encoding="utf-8"))
    assert [[a["attempt"] for a in d] for d in meta["validator"]] == [[0], [0, 1], [0]]


def test_parallel_worker_error_keeps_other_angles(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "DRAFT_WORKERS", 3)
    shown = {0: threading.Event(), 2: threading.Event()}

    def before(angle, attempt):
        if angle == 1:  # fail only once angles 1 and 3 have finished and been reported
            assert all(e.wait(5) for e in shown.values())

    def on_event(name, payload):
        if name == "draft" and payload["angle"] in shown:
            shown[payload["angle"]].set()

    client = AngleClient([[POSTS[0]], [RuntimeError("boom")], [POSTS[2]]], before)
    with pytest.raises(RuntimeError, match="boom"):
        run_brief(BRIEF, client=client, out_root=tmp_path, on_event=on_event)
    (run_dir,) = run_dirs(tmp_path)
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "error" and "RuntimeError: boom" in meta["error"]
    assert [len(d) for d in meta["validator"]] == [1, 0, 1]
    assert (run_dir / "draft-1.md").is_file() and not (run_dir / "draft-2.md").exists() and (run_dir / "draft-3.md").is_file()
    assert [c["input_tokens"] for c in meta["usage"]["calls"]] == [100, 200, 202]  # the failed call reported no usage


def test_abort_in_on_event_does_not_wait_for_in_flight_calls(tmp_path, monkeypatch):
    # Streamlit's rerun exception arrives inside on_event, on the main thread, while other drafts are still in flight
    monkeypatch.setattr(generate, "DRAFT_WORKERS", 3)
    release = threading.Event()

    def before(angle, attempt):
        if angle != 0:
            release.wait(10)  # angles 2 and 3 hang until the test lets them go

    def on_event(name, payload):
        if name == "draft":
            raise KeyboardInterrupt

    client = AngleClient([[POSTS[0]], [POSTS[1]], [POSTS[2]]], before)
    try:
        with pytest.raises(KeyboardInterrupt):
            run_brief(BRIEF, client=client, out_root=tmp_path, on_event=on_event)  # returns while two calls hang
        (run_dir,) = run_dirs(tmp_path)
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["status"] == "error" and "KeyboardInterrupt" in meta["error"]
        assert [len(d) for d in meta["validator"]] == [1, 0, 0]
    finally:
        release.set()


def test_finished_ads_get_a_photo_failed_ones_do_not(tmp_path, photos, serial):
    result, _ = run(FakeClient(ANGLES, GOOD, BAD), tmp_path)  # angle 1 passes; angles 2 and 3 never do
    run_dir = Path(result.run_dir)
    image = generate.pick_image(result.run_id, 0)
    assert image.parent == photos and image.suffix in {".png", ".jpg"}
    assert (run_dir / f"draft-1{image.suffix}").read_bytes() == image.read_bytes()
    assert (run_dir / "draft-1.md").read_text(encoding="utf-8").startswith(f"![](draft-1{image.suffix})\n\n")
    assert not any(run_dir.glob("draft-2.*g")) and "![]" not in (run_dir / "draft-2.md").read_text(encoding="utf-8")


def test_pick_image_is_random_but_stable(photos):
    picks = {generate.pick_image(f"run-{n}", a) for n in range(20) for a in range(3)}
    assert {p.name for p in picks} == {"demo-road.png", "launch-truck.jpg"}  # both listed photos get used, never an unlisted file
    assert generate.pick_image("run-1", 2) == generate.pick_image("run-1", 2)  # the app and the run folder agree


def test_no_photos_folder_means_no_image(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "PHOTOS", tmp_path / "missing")
    assert generate.pick_image("run", 0) is None
    result, _ = run(FakeClient(ANGLES, GOOD), tmp_path)
    assert not (Path(result.run_dir) / "draft-1.md").read_text(encoding="utf-8").startswith("![]")
