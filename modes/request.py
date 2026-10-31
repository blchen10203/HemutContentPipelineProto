"""Mode A: a Hemut person asks for a post. request_to_brief() turns the Request into a Brief; run_request() runs it.

Gap rule: anything the request mentions that no claim covers goes in Brief.needs_source, and run_brief() stops there.
Nothing is web-searched or guessed.
"""
import time
from typing import Literal

import anthropic
from pydantic import create_model

from generate import OUT, ask, load_prompt, run_brief, system_prompt, write_failed_request
from knowledge.loader import load_audiences, load_claims, load_features, load_voice
from schemas import AudienceProfile, Brief, CallUsage, Claim, Feature, Request, RunResult, VoiceRules


def request_to_brief(
    request: Request, claims: dict[str, Claim], *, voice: VoiceRules | None = None,
    audiences: dict[str, AudienceProfile] | None = None,
    features: dict[str, Feature] | None = None, client: anthropic.Anthropic | None = None,
    usage: list[CallUsage] | None = None,  # gets this call's token use
) -> Brief:
    audiences = load_audiences() if audiences is None else audiences
    personas = "\n".join(f"- {a.id}: {a.label}. {a.role}" for a in audiences.values())
    features = load_features() if features is None else features
    picked = features.get(request.feature_id) if request.feature_id else None
    if request.feature_id and picked is None:
        raise ValueError(f"Request feature_id {request.feature_id!r} is not in knowledge/features.yaml")
    if picked:
        feature = (f"The requester picked this feature. Set feature_id to {picked.id} and build the brief around it: "
                   f"{picked.label}: {picked.hemut_feature}")
    else:
        feature = ("Set feature_id to the id of the feature below that the request is about, or leave it empty if none fits.\n"
                   + "\n".join(f"- {f.id}: {f.label}" for f in features.values()))
    prompt = load_prompt("normalize.txt", personas=personas, request=request.text, notes=request.notes or "(none)", feature=feature)
    # The response schema only allows real persona ids, so the model cannot return one that does not exist.
    shape = create_model("RequestBrief", __base__=Brief, audience_id=(Literal[tuple(audiences)], ...),
                         feature_id=(Literal[tuple(features)] | None, None))
    reply = ask(client or anthropic.Anthropic(), system_prompt(claims, voice or load_voice()), [{"role": "user", "content": prompt}], shape,
                step="normalize", usage=[] if usage is None else usage)
    brief = Brief.model_validate_json(reply).model_copy(update={"origin": "request", "origin_ref": None})
    # An id the model made up means it thinks something is covered that is not: that is a gap, not a typo to drop.
    unknown = [i for i in brief.claim_ids if i not in claims]
    known = [i for i in brief.claim_ids if i in claims]
    if picked:  # the pick overrides whatever the model chose; its claims are added to the model's
        brief = brief.model_copy(update={"feature_id": picked.id, "hemut_feature": picked.hemut_feature})
        known = list(dict.fromkeys(known + picked.claim_ids))
    return brief.model_copy(update={
        "claim_ids": known,
        "needs_source": brief.needs_source + [f"no claim with id {i!r}" for i in unknown],
    })


def run_request(
    request: Request,
    *,
    claims: dict[str, Claim] | None = None,
    voice: VoiceRules | None = None,
    client: anthropic.Anthropic | None = None,
    **run_kwargs,  # on_event, out_root
) -> RunResult:
    started = time.perf_counter()  # meta.json duration_s counts the normalize call too
    claims = load_claims() if claims is None else claims
    voice = load_voice() if voice is None else voice
    client = client or anthropic.Anthropic()
    usage: list[CallUsage] = []
    try:
        brief = request_to_brief(request, claims, voice=voice, client=client, usage=usage)
    except BaseException as e:  # same as run_brief: an aborted run still leaves its folder
        write_failed_request(e, claims, run_kwargs.get("out_root", OUT), usage, started)
        raise
    return run_brief(brief, claims=claims, voice=voice, client=client, usage=usage, started=started, **run_kwargs)
