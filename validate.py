"""Deterministic checks on drafts. No LLM.

parse_post(raw) builds a TrxckwrldPost from model output and reports why it can't.
validate(post, claims, voice) checks the RENDERED text: claim ids and placeholders, unbacked numbers,
retired and unknown product names, banned (absolute / deceptive) phrases, customer voice, and the
approval flag. needs_approval(post, claims) tells callers how to set that flag.
"""
import re

from pydantic import ValidationError

from schemas import Claim, PlaceholderError, TrxckwrldPost, Violation, VoiceRules, render_post, used_claim_ids

_NUMBER_WORDS = (
    "two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    "seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    "million|billion|dozen|half|halves|twice"
)  # bare "one" is allowed: "one place", "one system"
NUMBER = re.compile(  # s? so "thousands of fleets" counts too
    rf"\$?\d(?:[\d,.]*\d)?%?|[$%]|\b(?:{_NUMBER_WORDS})s?(?:[-\s]+(?:{_NUMBER_WORDS})s?)*\b", re.IGNORECASE
)
# [ \t]+, not \s+: render_post joins title, body and CTA with blank lines, and "Command\n\nStart" is not a product.
# Lookahead so "Hemut Command Pro" yields both pairs.
PRODUCT_MENTION = re.compile(r"\b(?=((Hemut|Command)[ \t]+([A-Z][\w-]*)))")

QUOTE = re.compile(r'["“]([^"“”\n]+)["”]')
FIRST_PERSON = re.compile(
    r"\bI(?:'ve| have)? (?:switched|moved|signed up|started using|tried|use|run|saved|love|recommend)\b"
    r"|\bI'?m an? (?:driver|trucker|dispatcher|owner[- ]operator|fleet owner|carrier)\b"
    r"|\bas an? (?:driver|trucker|dispatcher|owner[- ]operator|fleet owner|carrier),? I\b"
    r"|\bmy (?:fleet|trucks?|rigs?|drivers|dispatchers?|company|business|loads?|operation)\b"
    r"|\bour (?:fleet|trucks?|rigs?|drivers|dispatchers|loads)\b",  # "our team" / "our pricing" is Hemut speaking
    re.IGNORECASE,
)
TESTIMONIAL = re.compile(
    r"\b(?!Hemut\b|Hemi\b)[A-Z][a-z]+(?: [A-Z][a-z.]+)*,? (?:says|said)\b"
    r"|\b(?:says|said) (?!Hemut\b|Hemi\b)[A-Z][a-z]+\b"
    r"|\baccording to (?!Hemut\b)[A-Z][a-z]+ [A-Z][a-z]+"
    r"|[★☆⭐]|\b\d(?:\.\d)?\s*(?:/\s*5|stars?)\b|\bfive[- ]stars?\b"
)


def parse_post(raw: dict) -> tuple[TrxckwrldPost | None, list[Violation]]:
    try:
        return TrxckwrldPost.model_validate(raw), []
    except ValidationError as e:
        violations = []
        for err in e.errors():
            loc = ".".join(str(part) for part in err["loc"]) or "post"
            utm = err["loc"] == ("cta_url",) and err["type"] == "value_error"
            violations.append(Violation(
                code="MISSING_UTM" if utm else "PARSE_ERROR",
                message=f"{loc}: {err['msg']}",
                span=str(err["input"]) if utm else None,
            ))
        return None, violations


def needs_approval(post: TrxckwrldPost, claims: dict[str, Claim]) -> bool:
    return any(claims[i].requires_approval for i in used_claim_ids(post) if i in claims)


def validate(post: TrxckwrldPost, claims: dict[str, Claim], voice: VoiceRules) -> list[Violation]:
    used = used_claim_ids(post)
    out = [
        Violation(code="UNKNOWN_CLAIM", message=f"claim id {i!r} is not in claims.yaml", span=i)
        for i in sorted((used | set(post.claim_ids_used)) - claims.keys())
    ]
    try:
        text = render_post(post, claims)
    except PlaceholderError as e:
        if not used - claims.keys():  # an unknown id already explains the failure
            out.append(Violation(code="PLACEHOLDER_ERROR", message=str(e)))
        return out  # nothing rendered, so there is no text to check
    if set(post.claim_ids_used) != used:
        out.append(Violation(
            code="PLACEHOLDER_ERROR",
            message=f"claim_ids_used {sorted(post.claim_ids_used)} does not match the claims in the copy {sorted(used)}",
        ))

    text = text.replace(post.cta_url, " ")  # UTM values carry digits
    free_text = text  # copy with the claim wording taken out: whatever is left was written freely
    for phrasing in sorted({p for i in used for p in claims[i].phrasings}, key=len, reverse=True):
        free_text = free_text.replace(phrasing, "\n")

    out += [_v("UNBACKED_NUMBER", "number not backed by a claim placeholder", m[0]) for m in NUMBER.finditer(free_text)]
    out += _retired_names(text, voice)
    out += _unknown_products(free_text, voice)
    out += _banned_words(text, voice)
    out += _customer_voice(free_text)
    if post.requires_approval != needs_approval(post, claims):
        out.append(Violation(
            code="APPROVAL_FLAG_WRONG",
            message=f"requires_approval is {post.requires_approval}, but the claims used say {not post.requires_approval}",
        ))
    return out


def _v(code: str, message: str, span: str) -> Violation:
    return Violation(code=code, message=f"{message}: {span!r}", span=span)


def _retired_names(text: str, voice: VoiceRules) -> list[Violation]:
    out, taken = [], []
    for name in voice.retired_names:
        n = re.escape(name)
        # "Hemut Core" in any case; bare "Core" only as capitalized, so "reach out" is fine.
        for m in [*re.finditer(rf"\bHemut\s+{n}\b", text, re.IGNORECASE), *re.finditer(rf"\b{n}\b", text)]:
            if not any(a <= m.start() < b for a, b in taken):
                taken.append(m.span())
                out.append(_v("RETIRED_NAME", "retired product name", m[0]))
    return out


def _unknown_products(free_text: str, voice: VoiceRules) -> list[Violation]:
    allowed = set(voice.allowed_product_names)
    return [
        _v("UNKNOWN_PRODUCT", "not a current product name", m[1])
        for m in PRODUCT_MENTION.finditer(free_text)
        if m[1] not in allowed and not (m[2] == "Hemut" and m[3] in allowed)
    ]


def _banned_words(text: str, voice: VoiceRules) -> list[Violation]:
    # Boundary at the start only, and a custom one so "#1" and "100%" can match: "guarantee" catches "guaranteed".
    return [
        _v("BANNED_WORD", "banned phrase (absolute or deceptive claim)", m[0])
        for w in voice.banned_words
        for m in re.finditer(rf"(?<![\w#$%]){re.escape(w)}\w*", text, re.IGNORECASE)
    ]


def _customer_voice(free_text: str) -> list[Violation]:
    spans = [m[0] for m in QUOTE.finditer(free_text) if len(m[1].split()) >= 4]  # "rate con" is a term, not speech
    spans += [m[0] for m in FIRST_PERSON.finditer(free_text)] + [m[0] for m in TESTIMONIAL.finditer(free_text)]
    return [_v("CUSTOMER_VOICE", "reads as customer or driver voice, not Hemut", s) for s in dict.fromkeys(spans)]
