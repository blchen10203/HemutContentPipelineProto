"""Pydantic v2 models that are the contract between modules.

Knowledge base: Claim (one entry of claims.yaml), VoiceRules (voice.yaml).
Still to come: Brief, TrxckwrldPost, StatCard.
"""
import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo'd key in claims.yaml fails instead of vanishing

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    type: Literal["price", "product", "feature", "metric", "company", "competitor"]
    value: int | float | str
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
    banned_words: list[str]
    vocabulary: list[str]
