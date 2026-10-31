"""Pydantic v2 models that are the contract between modules, plus claim-placeholder rendering.

Knowledge base: Claim (one entry of claims.yaml), VoiceRules (voice.yaml), AudienceProfile (audiences.yaml).
Mode A input:   Request.
Core:           Brief, Angle, StatCard, TrxckwrldPost, Violation, DraftAttempt, CallUsage, RunResult.
Mode B:         SeasonWindow, BridgeEntry, PlanItem.
Features:       Screenshot, Feature (features.yaml).

Copy never contains free numbers or claim text. It references claims as {{claim:<id>}} (first phrasing)
or {{claim:<id>:<n>}} (nth phrasing, 0-based); render_post() fills them from claims.yaml.
"""
import calendar
import datetime
import re
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator, model_validator


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo'd key in claims.yaml fails instead of vanishing

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    type: Literal["price", "product", "feature", "metric", "deadline", "company", "competitor"]  # deadline: e.g. IFTA due dates
    value: StrictInt | StrictFloat | str  # strict: YAML true/yes must not become the number 1
    unit: str | None = None
    phrasings: list[str]  # empty = record only, never in copy; allowed only for non-numeric product/feature/company
    context: str | None = None
    source_url: str = Field(pattern=r"^https?://")
    source_snapshot: str  # repo-relative, e.g. knowledge/sources/pricing_2026-10-23.txt
    checked: datetime.date
    requires_approval: bool

    @model_validator(mode="after")
    def _numbers_need_phrasings(self):
        # Only descriptive, non-numeric claims may be record-only (e.g. testimonials kept for traceability).
        if not self.phrasings and (self.type not in {"product", "feature", "company"} or not isinstance(self.value, str)):
            raise ValueError(f"{self.type} claim with value {self.value!r} needs at least one phrasing")
        return self


class VoiceRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_product_names: list[str] = Field(min_length=1)
    retired_names: list[str]
    competitor_names: list[str]
    allowed_competitor_phrases: list[str]
    banned_words: list[str]
    vocabulary: list[str]


# Persona and bridge text (CLAUDE.md research/ rule) guides the writer and is never copy: no numbers, dates, quotes
# or first-person speech can leak from it.
_GUIDANCE_BANNED = [
    (re.compile(r"\d"), "a digit"),
    (re.compile('["“”]'), "a quotation mark"),
    (re.compile(r"\b(?:I|[Mm]e|[Mm]y|[Mm]ine|[Ww]e|[Oo]urs?|[Uu]s)\b"), "first-person text"),
    (re.compile(r"\b(?:" + "|".join(calendar.month_name[1:]) + r")\b"), "a month name"),
]


def _guidance_only(owner: str, texts: list[str]) -> None:
    for text in texts:
        for pattern, what in _GUIDANCE_BANNED:
            if pattern.search(text):
                raise ValueError(f"{owner}: {what} in {text!r}; this text has no numbers, dates or quoted/first-person speech")


class AudienceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z]+(-[a-z]+)*$")
    label: str
    role: str
    pains: list[str] = Field(min_length=1)
    objections: list[str]
    tone_notes: list[str]

    @model_validator(mode="after")
    def _writer_guidance_only(self):
        _guidance_only(f"persona {self.id!r}", [self.label, self.role, *self.pains, *self.objections, *self.tone_notes])
        return self


# ---------------------------------------------------------------- Mode A input

# The trust boundary for typed user input; app.py does no validation of its own.
class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)  # so min_length rejects blank text

    text: str = Field(min_length=1)
    notes: str | None = None
    feature_id: str | None = None  # the feature the requester picked; None lets the model choose


# ---------------------------------------------------------------- Core

class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: Literal["request", "seasonal", "evergreen"]
    audience: str  # e.g. "5-15 truck fleets": the requester's words in Mode A, the persona label in Mode B
    audience_id: str  # AudienceProfile id; its pains, objections and tone go into the angles and draft prompts
    pain: str
    hemut_feature: str
    format: Literal["reddit_post", "social_post", "short_ad", "stat_card"]
    claim_ids: list[str]
    needs_source: list[str] = []
    sensitivity: Literal["low", "high"] = "low"
    origin_ref: str | None = None  # season id or evergreen tag
    feature_id: str | None = None  # features.yaml id; picks the ad's screenshot


class Angle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: str
    pain: str
    feature: str
    claim_ids: list[str]


class StatCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str  # the number always comes from this claim's first phrasing, never from the label
    label: str


CTA_PAGES = {"https://command.hemut.com/signup", "https://hemut.com/pricing"}  # the only links system.txt allows


class TrxckwrldPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    cta_text: str
    cta_url: str
    claim_ids_used: list[str]
    stat_card: StatCard | None = None
    requires_approval: bool = False

    @field_validator("cta_url")
    @classmethod
    def _has_utm(cls, url: str) -> str:
        parts = urlsplit(url)
        params = parse_qs(parts.query)  # blank values are dropped, so "utm_source=" counts as missing
        missing = [k for k in ("utm_source", "utm_medium", "utm_campaign") if k not in params]
        if parts.scheme not in ("http", "https") or missing:
            raise ValueError(f"cta_url must be an http(s) URL with utm_source, utm_medium and utm_campaign; missing {missing}")
        page = f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/")
        if page not in CTA_PAGES or params["utm_source"] != ["trxckwrld"]:
            raise ValueError(f"cta_url must be one of {sorted(CTA_PAGES)} with utm_source=trxckwrld, got {url!r}")
        return url


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "UNBACKED_NUMBER", "RETIRED_NAME", "UNKNOWN_PRODUCT", "COMPETITOR_NAME", "BANNED_WORD", "CUSTOMER_VOICE",
        "MISSING_UTM", "UNKNOWN_CLAIM", "PLACEHOLDER_ERROR", "PARSE_ERROR",
    ]
    message: str
    span: str | None = None


class DraftAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int
    raw_post: TrxckwrldPost | None = None
    rendered_text: str | None = None
    violations: list[Violation]


class CallUsage(BaseModel):
    """Token use of one API call, as response.usage reported it."""
    model_config = ConfigDict(extra="forbid")

    step: Literal["normalize", "angles", "draft"]
    model: str
    input_tokens: int  # uncached input only
    output_tokens: int  # includes thinking
    thinking_tokens: int | None = None  # the part of output_tokens spent thinking; None if the API did not report it
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    duration_s: float  # wall time of the API call alone


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_dir: str
    status: Literal["ok", "needs_source", "failed_validation", "blocked_sensitive", "error"]  # error: API/auth failure or aborted run
    brief: Brief | None = None
    angles: list[Angle] = []
    drafts: list[list[DraftAttempt]] = []  # one attempt list per angle
    needs_source: list[str] = []
    usage: list[CallUsage] = []  # every API call of the run, in order, refused ones included


# ---------------------------------------------------------------- Mode B

class SeasonWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    start: str = Field(pattern=r"^\d{2}-\d{2}$")  # MM-DD; start after end means the window wraps past Dec 31
    end: str = Field(pattern=r"^\d{2}-\d{2}$")
    lead_days: int = Field(ge=0)  # how many days before start to begin advertising
    source_url: str = Field(pattern=r"^https?://")
    checked: datetime.date
    verified_by: str | None = None

    @field_validator("start", "end")
    @classmethod
    def _real_month_day(cls, value: str) -> str:
        try:
            datetime.datetime.strptime(f"2000-{value}", "%Y-%m-%d")  # leap year, so 02-29 is allowed
        except ValueError:
            raise ValueError(f"{value!r} is not a real MM-DD date") from None
        return value


class BridgeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str  # season id or "evergreen-<pillar>"
    pain: str
    hemut_feature: str
    claim_ids: list[str]
    feature: str  # features.yaml id this angle sells
    audiences: list[str] = []  # AudienceProfile ids this angle fits; empty means any

    @model_validator(mode="after")
    def _writer_guidance_only(self):  # pain and hemut_feature reach the draft model as part of the Brief
        _guidance_only(f"bridge {self.tag!r}", [self.pain, self.hemut_feature])
        return self


class Screenshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(pattern=r"^[A-Za-z0-9][\w.-]*\.(png|jpe?g|webp)$")  # a bare file name in assets/screenshots/
    on_screen: str  # what the screen shows, read by the draft model


class Feature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    label: str
    hemut_feature: str
    claim_ids: list[str]
    screenshots: list[Screenshot] = []

    @model_validator(mode="after")
    def _writer_guidance_only(self):  # label, hemut_feature and on_screen reach the draft model
        _guidance_only(f"feature {self.id!r}", [self.label, self.hemut_feature, *(s.on_screen for s in self.screenshots)])
        return self


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: Brief
    reason: str  # plain English, e.g. "IFTA Q4 deadline Jan 31 is 12 days out"


# ---------------------------------------------------------------- Claim placeholders

PLACEHOLDER = re.compile(r"\{\{claim:([a-z0-9]+(?:-[a-z0-9]+)*)(?::(\d+))?\}\}")


class PlaceholderError(ValueError):
    """A {{claim:...}} placeholder that cannot be filled from claims.yaml."""


def used_claim_ids(post: TrxckwrldPost) -> set[str]:
    """Claim ids referenced by the post's placeholders (stat card label included), plus its stat card's claim:
    everything render_post fills."""
    label = post.stat_card.label if post.stat_card else ""
    ids = {m[1] for m in PLACEHOLDER.finditer("\n".join([post.title, post.body, post.cta_text, label]))}
    if post.stat_card:
        ids.add(post.stat_card.claim_id)
    return ids


def render_post(post: TrxckwrldPost, claims: dict[str, Claim]) -> str:
    """Title, body, optional stat card ("<label>: <first phrasing>") and CTA, with every placeholder filled."""
    parts = [post.title, post.body]
    if post.stat_card:
        parts.append(f"{post.stat_card.label}: {{{{claim:{post.stat_card.claim_id}}}}}")
    parts.append(f"{post.cta_text} {post.cta_url}")

    def fill(m: re.Match) -> str:
        claim, n = claims.get(m[1]), int(m[2] or 0)
        if claim is None:
            raise PlaceholderError(f"{m[0]}: unknown claim id")
        if not claim.phrasings:
            raise PlaceholderError(f"{m[0]}: claim has no phrasings, so it can never appear in copy")
        if n >= len(claim.phrasings):
            raise PlaceholderError(f"{m[0]}: claim has only {len(claim.phrasings)} phrasing(s)")
        return claim.phrasings[n]

    text = PLACEHOLDER.sub(fill, "\n\n".join(parts))
    if "{{" in text:  # anything left is a placeholder the pattern rejected, e.g. {{claim:Bad_Id}} or {{price}}
        raise PlaceholderError(f"malformed placeholder near {text[text.index('{{'):][:40]!r}")
    return text
