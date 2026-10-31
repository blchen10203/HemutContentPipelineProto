"""Core pipeline, shared by both modes: Brief -> angles -> draft -> validate -> retry (max 2). Writes out/runs/<id>/.

run_brief(brief) never posts anything. on_event(name, payload) reports progress for the CLI and Streamlit:
"brief", "angles", "draft" (one per attempt), "done". If the API fails mid-run, the run folder is still written, then the
error is re-raised. The same goes for a BaseException (Ctrl+C, or Streamlit's rerun when a widget is clicked mid-run).
The angles' draft chains run in parallel threads; on_event is still only called from the thread that called run_brief().
"""
import datetime
import hashlib
import json
import os
import queue
import random
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable

import anthropic
import yaml
from pydantic import BaseModel

from knowledge.build_fact_sheet import render as render_fact_sheet
from knowledge.loader import ROOT, load_audiences, load_claims, load_features, load_voice
from schemas import Angle, AudienceProfile, Brief, CallUsage, Claim, DraftAttempt, RunResult, TrxckwrldPost, Violation, VoiceRules, render_post
from validate import needs_approval, parse_post, validate

MODEL = "claude-opus-5-5"  # no server-side fallback, so this is always the model that answered
EFFORT = "medium"  # Opus 5.5 rejects temperature; effort is the only sampling-side control
N_ANGLES = 3
DRAFT_WORKERS = N_ANGLES  # one thread per angle's draft chain
MAX_RETRIES = 2
PROMPTS = ROOT / "prompts"
OUT = ROOT / "out" / "runs"
PHOTOS = ROOT / "assets" / "hemut-brand" / "photos"  # local only (gitignored): no folder means ads get no image
# Photos someone looked at: no people, no customer brands, no product artwork. A file not listed here is never used
# (core-page_hero-bg.png shows a customer's truck and two people; the Forge and Custom files are product artwork).
PHOTO_NAMES = ["command-page_hero-bg.png", "cta-truck.png", "custom-page_hero-background.png", "demo-road.png",
               "future-road.jpg", "hero-landscape.png", "launch-truck.jpg", "onboarding-truck.png", "roi-truck.png",
               "solutions-warehouse.png"]
SCREENSHOTS = ROOT / "assets" / "screenshots"
SCREENSHOT_NOTE = "The ad shows this Hemut screenshot: {note}. The copy may point at what it shows; facts still come only from the fact sheet."
NO_SCREENSHOT = "The ad shows a brand photo or no image. Do not refer to the image."
RUN_ID = "%Y%m%d-%H%M%S-%f"
# USD per million tokens, from Anthropic's model docs (2026-10-06). cache_write is the 5-minute TTL rate (1.25x input).
PRICES = {"claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00}}


class _Angles(BaseModel):  # response shape for the angles call only
    angles: list[Angle]


class Refused(Exception):
    """The model stopped without a usable answer (refusal or max_tokens)."""


def run_brief(
    brief: Brief,
    *,
    claims: dict[str, Claim] | None = None,
    voice: VoiceRules | None = None,
    client: anthropic.Anthropic | None = None,
    on_event: Callable[[str, dict], None] = lambda name, payload: None,
    out_root: Path = OUT,
    usage: list[CallUsage] | None = None,  # calls made before the Brief existed (Mode A's normalize step)
    started: float | None = None,  # time.perf_counter() at the start of the run, if it began earlier (Mode A's normalize)
) -> RunResult:
    started = time.perf_counter() if started is None else started
    claims = load_claims() if claims is None else claims  # the knowledge base is always loaded
    voice = load_voice() if voice is None else voice
    now = datetime.datetime.now()
    run_dir = out_root / now.strftime(RUN_ID)
    result = RunResult(run_id=run_dir.name, run_dir=str(run_dir), status="ok", brief=brief, needs_source=brief.needs_source,
                       usage=usage or [])
    on_event("brief", brief.model_dump())

    if brief.needs_source:
        result.status = "needs_source"
    elif brief.sensitivity == "high":
        result.status = "blocked_sensitive"
    else:
        try:
            _generate(brief, result, claims, voice, client or anthropic.Anthropic(), on_event)
        except BaseException as e:  # incl. Streamlit's rerun exception, so an aborted run keeps its folder
            _write_error(run_dir, result, claims, now, started, e)
            raise

    _write_run(run_dir, result, claims, now, started)
    on_event("done", {"status": result.status, "run_dir": str(run_dir)})
    return result


def write_failed_request(error: BaseException, claims: dict[str, Claim], out_root: Path = OUT, usage: list[CallUsage] = (),
                         started: float | None = None) -> None:
    """A Mode A run that failed before it had a Brief (the request -> Brief call) still leaves meta.json."""
    now = datetime.datetime.now()
    run_dir = out_root / now.strftime(RUN_ID)
    result = RunResult(run_id=run_dir.name, run_dir=str(run_dir), status="error", usage=list(usage))
    _write_error(run_dir, result, claims, now, time.perf_counter() if started is None else started, error)


def _write_error(run_dir: Path, result: RunResult, claims: dict[str, Claim], now: datetime.datetime, started: float,
                 e: BaseException) -> None:
    result.status = "error"
    _write_run(run_dir, result, claims, now, started, error=f"{type(e).__name__}: {e}")
    e.add_note(f"run folder: {run_dir}")


def _generate(brief, result, claims, voice, client, on_event) -> None:
    system = system_prompt(claims, voice)
    brief_json = brief.model_dump_json(indent=2)
    if not (audience := load_audiences().get(brief.audience_id)):
        raise ValueError(f"Brief audience_id {brief.audience_id!r} is not in knowledge/audiences.yaml")
    persona = render_persona(audience)
    reply = ask(client, system, [_user(load_prompt("angles.txt", n=str(N_ANGLES), persona=persona, brief=brief_json))], _Angles,
                step="angles", usage=result.usage)
    result.angles = _Angles.model_validate_json(reply).angles
    on_event("angles", {"angles": [a.model_dump() for a in result.angles]})

    # The angles call above runs alone first; then one thread per angle runs its draft chain (with retries).
    # Each worker fills only its own drafts[i] and usages[i]; events go through a queue so on_event stays on this thread.
    result.drafts = [[] for _ in result.angles]  # filled in place, so an error keeps the attempts made so far
    usages: list[list[CallUsage]] = [[] for _ in result.angles]
    events: queue.Queue = queue.Queue()
    stop = threading.Event()
    pool = ThreadPoolExecutor(max_workers=DRAFT_WORKERS)
    try:
        pending = set()
        for i, angle in enumerate(result.angles):
            image = pick_image(result.run_id, i, brief.feature_id)
            screen = SCREENSHOT_NOTE.format(note=image[1]) if image and image[1] else NO_SCREENSHOT
            first = load_prompt("draft.txt", persona=persona, brief=brief_json, angle=angle.model_dump_json(indent=2), screen=screen)
            on_attempt = lambda a, i=i: events.put(("draft", {"angle": i, **a}))
            pending.add(pool.submit(_draft, client, system, first, claims, voice, result.drafts[i], on_attempt, usages[i], stop))
        while pending:
            done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            _drain(events, on_event)  # Streamlit's rerun exception surfaces here
            for future in done:
                future.result()  # re-raises a worker's error
    except BaseException:
        stop.set()  # in-flight workers make no further API calls
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)  # an abort does not wait for in-flight calls
        result.drafts = [list(d) for d in result.drafts]  # a worker still in flight after an abort cannot change what is written
        result.usage += [c for u in usages for c in u]  # angle order
    if not any(attempts and attempts[-1].violations == [] for attempts in result.drafts):
        result.status = "failed_validation"


def _drain(events: queue.Queue, on_event) -> None:
    while True:
        try:
            name, payload = events.get_nowait()
        except queue.Empty:
            return
        on_event(name, payload)


def _draft(client, system, first_prompt, claims, voice, attempts: list[DraftAttempt], on_attempt, usage: list[CallUsage],
           stop: threading.Event) -> None:
    messages = [_user(first_prompt)]
    for n in range(1 + MAX_RETRIES):
        if stop.is_set():
            return
        try:
            reply = ask(client, system, messages, TrxckwrldPost, step="draft", usage=usage)
        except Refused as e:  # retrying the same request will not help
            attempts.append(DraftAttempt(attempt=n, violations=[Violation(code="PARSE_ERROR", message=str(e))]))
            on_attempt({"attempt": n, "violations": [v.model_dump() for v in attempts[-1].violations]})
            break
        try:
            post, violations = parse_post(json.loads(reply))
        except json.JSONDecodeError as e:
            post, violations = None, [Violation(code="PARSE_ERROR", message=f"not JSON: {e}")]
        text = None
        if post:
            post = post.model_copy(update={"requires_approval": needs_approval(post, claims)})  # derived, not the model's call
            violations = validate(post, claims, voice)
            if not violations:
                text = render_post(post, claims)
        attempts.append(DraftAttempt(attempt=n, raw_post=post, rendered_text=text, violations=violations))
        on_attempt({"attempt": n, "violations": [v.model_dump() for v in violations]})
        if not violations:
            break
        messages += [
            {"role": "assistant", "content": reply},
            _user("The validator rejected that draft:\n" + "\n".join(f"- {v.code}: {v.message}" for v in violations)
                  + "\nWrite the whole post again with these fixed."),
        ]


def ask(client, system: str, messages: list, shape: type[BaseModel], *, step: str, usage: list[CallUsage]) -> str:
    """One structured-output call; returns the JSON text and appends its token use to usage.
    Raises Refused if the model gave no usable answer."""
    start = time.perf_counter()
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],  # same prefix on every call
        messages=messages,
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": anthropic.transform_schema(shape)}},
    )
    duration_s = round(time.perf_counter() - start, 3)  # the API call only, not the parsing below
    u = response.usage
    usage.append(CallUsage(  # before the refusal check: a refused call is still billed
        step=step, model=response.model, duration_s=duration_s, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
        thinking_tokens=getattr(u.output_tokens_details, "thinking_tokens", None),
        cache_read_input_tokens=u.cache_read_input_tokens or 0, cache_creation_input_tokens=u.cache_creation_input_tokens or 0,
    ))
    if response.stop_reason in ("refusal", "max_tokens"):
        raise Refused(f"model stopped with {response.stop_reason}")
    return next(b.text for b in response.content if b.type == "text")


def pick_image(run_id: str, angle: int, feature_id: str | None = None) -> tuple[Path, str | None] | None:
    """The image of a finished ad: (path, on_screen) for a feature screenshot, (path, None) for a photo. Random, but seeded
    by run and angle, so the app and the run folder agree."""
    rng = random.Random(f"{run_id}:{angle}")
    feature = load_features().get(feature_id)
    shots = [(SCREENSHOTS / s.file, s.on_screen) for s in feature.screenshots if (SCREENSHOTS / s.file).is_file()] if feature else []
    if shots:
        return rng.choice(shots)
    photos = [PHOTOS / name for name in PHOTO_NAMES if (PHOTOS / name).is_file()]
    return (rng.choice(photos), None) if photos else None


def usage_total(calls: list[CallUsage]) -> dict:
    """Token sums over calls and a USD estimate from PRICES. usd_estimate is None if a call's model has no price,
    thinking_tokens is None if any call did not report it (unknown, not zero)."""
    fields = ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"]
    total = {"calls": len(calls)} | {f: sum(getattr(c, f) for c in calls) for f in fields}
    total["thinking_tokens"] = None if any(c.thinking_tokens is None for c in calls) else sum(c.thinking_tokens for c in calls)
    total["usd_estimate"] = None if any(c.model not in PRICES for c in calls) else round(sum(map(_usd, calls)), 4)
    # Time spent in API calls. Drafts run in parallel, so this is more than the run's wall time (meta.json duration_s).
    total["call_seconds"] = round(sum(c.duration_s for c in calls), 3)
    return total


def _usd(c: CallUsage) -> float:
    p = PRICES[c.model]
    return (c.input_tokens * p["input"] + c.output_tokens * p["output"] + c.cache_read_input_tokens * p["cache_read"]
            + c.cache_creation_input_tokens * p["cache_write"]) / 1_000_000


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def load_prompt(name: str, **values: str) -> str:
    text = (PROMPTS / name).read_text(encoding="utf-8")
    for key, value in values.items():  # not str.format: prompts contain literal {{claim:<id>}}
        text = text.replace("{" + key + "}", value)
    return text


def render_persona(a: AudienceProfile) -> str:
    lists = [("Struggles with", a.pains), ("Hesitates because of", a.objections), ("Tone", a.tone_notes)]
    return f"{a.label}: {a.role}\n" + "\n".join(f"{name}:\n" + "\n".join(f"- {x}" for x in items) for name, items in lists if items)


def system_prompt(claims: dict[str, Claim], voice: VoiceRules) -> str:
    """Rules, voice and the whole fact sheet. Identical for every call in a run (and across modes), so it caches."""
    return load_prompt(
        "system.txt",
        product_names=", ".join(voice.allowed_product_names),
        retired_names=", ".join(voice.retired_names),
        competitor_names=", ".join(voice.competitor_names),
        banned_words=", ".join(f'"{w}"' for w in voice.banned_words),
        vocabulary=", ".join(voice.vocabulary),
        fact_sheet=render_fact_sheet(claims),  # rendered from the claims in use, so it always matches the validator
    )


def _write_run(run_dir: Path, result: RunResult, claims: dict[str, Claim], now: datetime.datetime, started: float,
               error: str | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    origin = result.brief.origin if result.brief else "request"  # no brief: Mode A failed while building it
    used = ["system.txt", "angles.txt", "draft.txt"] + (["normalize.txt"] if origin == "request" else [])
    meta = {
        "created": now.isoformat(timespec="seconds"),
        "duration_s": round(time.perf_counter() - started, 3),  # wall clock of the whole run, incl. Mode A's normalize call
        "mode": "A" if origin == "request" else "B",
        "brief_origin": origin,
        "status": result.status,
        "error": error,
        "model": MODEL,
        "effort": EFFORT,
        "temperature": None,  # not accepted by the model
        # read_text normalizes line endings, so the hash is the same on a CRLF checkout
        "prompt_versions": {p: hashlib.sha256(load_prompt(p).encode()).hexdigest()[:12] for p in used},
        "knowledge_checked": sorted({c.checked.isoformat() for c in claims.values()}),
        "validator": [[{"attempt": a.attempt, "violations": [v.model_dump() for v in a.violations]} for a in d] for d in result.drafts],
        "usage": {"calls": [c.model_dump() for c in result.usage], "total": usage_total(result.usage)},
    }
    (run_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    feature_id = result.brief.feature_id if result.brief else None
    meta["images"] = []
    try:  # meta.json is the cost record: written even if picking an image or a draft write fails
        for i, attempts in enumerate(result.drafts):
            meta["images"].append(None)
            if not attempts:
                continue
            last = attempts[-1]
            body = last.rendered_text or yaml.safe_dump(last.raw_post.model_dump() if last.raw_post else None, sort_keys=False)
            if last.rendered_text and (image := pick_image(result.run_id, i, feature_id)):  # only finished ads get an image
                path, note = image
                meta["images"][i] = {"image": path.name, "image_kind": "screenshot" if note else "photo"}
                try:  # linked, not copied: photos run up to 4 MB each
                    link = os.path.relpath(path, run_dir).replace(os.sep, "/")
                except ValueError:  # out_root on another Windows drive than assets/
                    link = path.as_uri()
                body = f"![]({link})\n\n{body}"
            flags = "".join(f"\n- {v.code}: {v.message}" for v in last.violations)
            (run_dir / f"draft-{i + 1}.md").write_text(body + (f"\n\n## Failed validation{flags}" if flags else ""), encoding="utf-8")
    finally:
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
