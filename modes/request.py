"""Mode A: a Hemut person asks for a post. request_to_brief() turns the Request into a Brief; run_request() runs it.

Gap rule: anything the request mentions that no claim covers goes in Brief.needs_source, and run_brief() stops there.
Nothing is web-searched or guessed.
"""
import anthropic

from generate import ask, load_prompt, run_brief, system_prompt
from knowledge.loader import load_claims, load_voice
from schemas import Brief, Claim, Request, RunResult, VoiceRules


def request_to_brief(
    request: Request, claims: dict[str, Claim], *, voice: VoiceRules | None = None, client: anthropic.Anthropic | None = None
) -> Brief:
    # TODO(cut list #3): turn request.sources into pending claims (requires_approval: true). Until then an attached
    # source does not cover anything: its items stay in needs_source, and the source text never reaches the model.
    prompt = load_prompt("normalize.txt", request=request.text, notes=request.notes or "(none)")
    reply = ask(client or anthropic.Anthropic(), system_prompt(claims, voice or load_voice()), [{"role": "user", "content": prompt}], Brief)
    brief = Brief.model_validate_json(reply).model_copy(update={"origin": "request", "origin_ref": None})
    # An id the model made up means it thinks something is covered that is not: that is a gap, not a typo to drop.
    unknown = [i for i in brief.claim_ids if i not in claims]
    return brief.model_copy(update={
        "claim_ids": [i for i in brief.claim_ids if i in claims],
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
    claims = load_claims() if claims is None else claims
    voice = load_voice() if voice is None else voice
    client = client or anthropic.Anthropic()
    brief = request_to_brief(request, claims, voice=voice, client=client)
    return run_brief(brief, claims=claims, voice=voice, client=client, **run_kwargs)
