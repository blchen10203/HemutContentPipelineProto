"""Validated input for the Add feature form (the form hands a NewFeature to add_feature())."""
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from schemas import _guidance_only


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class NewFeature(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    does: str
    url: str
    wordings: list[str]
    verified_by: str
    pain: str
    audiences: list[str]
    screenshot: bytes | None = None
    screenshot_ext: Literal["png", "jpg", "jpeg", "webp"] | None = None
    caption: str | None = None

    @property
    def id(self) -> str:
        return slugify(self.name)

    @field_validator("wordings", "audiences", mode="before")
    @classmethod
    def _strip_items(cls, v):
        return [s.strip() if isinstance(s, str) else s for s in v] if isinstance(v, list) else v

    @field_validator("wordings")
    @classmethod
    def _wordings(cls, v):
        v = [w for w in v if w]
        if not 1 <= len(v) <= 3:
            raise ValueError("give 1 to 3 non-blank wordings")
        return v

    @field_validator("audiences")
    @classmethod
    def _audiences(cls, v):
        if not v:
            raise ValueError("pick at least one audience")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v):
        u = urlsplit(v)
        host = u.hostname or ""
        if u.scheme != "https" or not (host == "hemut.com" or host.endswith(".hemut.com")):
            raise ValueError("must be an https link on hemut.com")
        return v

    @field_validator("verified_by")
    @classmethod
    def _verified_by(cls, v):
        if not re.fullmatch(r"[^()]+\(\s*[^()]+\s*\)", v):
            raise ValueError("write it as 'Name (Role)'")
        return v

    @field_validator("name", "does", "pain", "caption")
    @classmethod
    def _guidance(cls, v, info):
        if v is not None:
            _guidance_only(info.field_name, [v])
        return v

    @model_validator(mode="after")
    def _cross_checks(self):
        if not self.id:
            raise ValueError("name: has no letters or digits to make an id from")
        if self.screenshot is not None and (not self.screenshot_ext or not self.caption):
            raise ValueError("caption: required (with screenshot_ext) when a screenshot is given")
        if self.caption and self.screenshot is None:
            raise ValueError("caption: only allowed with a screenshot")
        return self
