"""Core pipeline, shared by both modes: Brief -> angles -> draft -> validate -> retry (max 2). Writes out/runs/<id>/.

run_brief(brief) never posts anything. on_event(name, payload) reports progress for the CLI and Streamlit:
"brief", "angles", "draft" (one per attempt), "done". If the API fails mid-run, the run folder is still written, then the
error is re-raised. The same goes for a BaseException (Ctrl+C, or Streamlit's rerun when a widget is clicked mid-run).
"""
import datetime
import hashlib
import json
from pathlib import Path
from typing import Callable

import anthropic
import yaml
from pydantic import BaseModel

from knowledge.build_fact_sheet import render as render_fact_sheet
from knowledge.loader import ROOT, load_audiences, load_claims, load_voice
from schemas import Angle, AudienceProfile, Brief, Claim, DraftAttempt, RunResult, TrxckwrldPost, Violation, VoiceRules, render_post
from validate import needs_approval, parse_post, validate

MODEL = "claude-opus-5-5"  # no server-side fallback, so this is always the model that answered
EFFORT = "medium"  # Opus 5.5 rejects temperature; effort is the only sampling-side control
N_ANGLES = 3
MAX_RETRIES = 2
PROMPTS = ROOT / "prompts"
OUT = ROOT / "out" / "runs"
RUN_ID = "%Y%m%d-%H%M%S-%f"


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
) -> RunResult:
    claims = load_claims() if claims is None else claims  # the knowledge base is always loaded
    voice = load_voice() if voice is None else voice
    now = datetime.datetime.now()
    run_dir = out_root / now.strftime(RUN_ID)
    result = RunResult(run_id=run_dir.name, run_dir=str(run_dir), status="ok", brief=brief, needs_source=brief.needs_source)
    on_event("brief", brief.model_dump())

    if brief.needs_source:
        result.status = "needs_source"
    elif brief.sensitivity == "high":
        result.status = "blocked_sensitive"
    else:
        try:
            _generate(brief, result, claims, voice, client or anthropic.Anthropic(), on_event)
        except BaseException as e:  # incl. Streamlit's rerun exception, so an aborted run keeps its folder
            _write_error(run_dir, result, claims, now, e)
            raise

    _write_run(run_dir, result, claims, now)
    on_event("done", {"status": result.status, "run_dir": str(run_dir)})
    return result


def write_failed_request(error: BaseException, claims: dict[str, Claim], out_root: Path = OUT) -> None:
    """A Mode A run that failed before it had a Brief (the request -> Brief call) still leaves meta.json."""
    now = datetime.datetime.now()
    run_dir = out_root / now.strftime(RUN_ID)
    _write_error(run_dir, RunResult(run_id=run_dir.name, run_dir=str(run_dir), status="error"), claims, now, error)


def _write_error(run_dir: Path, result: RunResult, claims: dict[str, Claim], now: datetime.datetime, e: BaseException) -> None:
    result.status = "error"
    _write_run(run_dir, result, claims, now, error=f"{type(e).__name__}: {e}")
    e.add_note(f"run folder: {run_dir}")


def _generate(brief, result, claims, voice, client, on_event) -> None:
    system = system_prompt(claims, voice)
    brief_json = brief.model_dump_json(indent=2)
    if not (audience := load_audiences().get(brief.audience_id)):
        raise ValueError(f"Brief audience_id {brief.audience_id!r} is not in knowledge/audiences.yaml")
    persona = render_persona(audience)
    reply = ask(client, system, [_user(load_prompt("angles.txt", n=str(N_ANGLES), persona=persona, brief=brief_json))], _Angles)
    result.angles = _Angles.model_validate_json(reply).angles
    on_event("angles", {"angles": [a.model_dump() for a in result.angles]})
    for i, angle in enumerate(result.angles):
        attempts: list[DraftAttempt] = []
        result.drafts.append(attempts)  # filled in place, so an API error keeps the attempts made so far
        first = load_prompt("draft.txt", persona=persona, brief=brief_json, angle=angle.model_dump_json(indent=2))
        _draft(client, system, first, claims, voice, attempts, lambda a: on_event("draft", {"angle": i, **a}))
    if not any(attempts and attempts[-1].violations == [] for attempts in result.drafts):
        result.status = "failed_validation"


def _draft(client, system, first_prompt, claims, voice, attempts: list[DraftAttempt], on_attempt) -> None:
    messages = [_user(first_prompt)]
    for n in range(1 + MAX_RETRIES):
        try:
            reply = ask(client, system, messages, TrxckwrldPost)
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


def ask(client, system: str, messages: list, shape: type[BaseModel]) -> str:
    """One structured-output call; returns the JSON text. Raises Refused if the model gave no usable answer."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],  # same prefix on every call
        messages=messages,
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": anthropic.transform_schema(shape)}},
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise Refused(f"model stopped with {response.stop_reason}")
    return next(b.text for b in response.content if b.type == "text")


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
        banned_words=", ".join(f'"{w}"' for w in voice.banned_words),
        vocabulary=", ".join(voice.vocabulary),
        fact_sheet=render_fact_sheet(claims),  # rendered from the claims in use, so it always matches the validator
    )


def _write_run(run_dir: Path, result: RunResult, claims: dict[str, Claim], now: datetime.datetime, error: str | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    origin = result.brief.origin if result.brief else "request"  # no brief: Mode A failed while building it
    used = ["system.txt", "angles.txt", "draft.txt"] + (["normalize.txt"] if origin == "request" else [])
    meta = {
        "created": now.isoformat(timespec="seconds"),
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
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (run_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    for i, attempts in enumerate(result.drafts):
        if not attempts:
            continue
        last = attempts[-1]
        body = last.rendered_text or yaml.safe_dump(last.raw_post.model_dump() if last.raw_post else None, sort_keys=False)
        flags = "".join(f"\n- {v.code}: {v.message}" for v in last.violations)
        (run_dir / f"draft-{i + 1}.md").write_text(body + (f"\n\n## Failed validation{flags}" if flags else ""), encoding="utf-8")
