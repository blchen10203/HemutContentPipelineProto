"""Validated input for the Add feature form (the form hands a NewFeature to add_feature())."""
import datetime
import io
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fetch_sources import snapshot
from knowledge.build_fact_sheet import render as render_fact_sheet
from knowledge.loader import ROOT, load_audiences, load_bridges, load_captions, load_claims, load_features, load_voice
from schemas import _guidance_only
from validate import SENSITIVE, _banned_words, _competitor_names, _customer_voice, _retired_names, _unknown_products


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class NewFeature(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1)
    does: str = Field(min_length=1)
    url: str
    wordings: list[str]
    verified_by: str
    pain: str = Field(min_length=1)
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
        if not re.fullmatch(r"[^()]+\(\s*[^()\s][^()]*\)", v):
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


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _block(entry: dict) -> str:
    return "\n" + yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)


def add_feature(f: NewFeature, *, root: Path = ROOT, today: datetime.date | None = None) -> tuple[str, list[Path]]:
    """Write f into claims, features, bridge_map, captions and the fact sheet; return its id and the changed or created
    files (relative to root, screenshot excluded: assets/ is gitignored). Any failure undoes everything."""
    today = today or datetime.date.today()
    k, fid = root / "knowledge", f.id
    sources, shots = k / "sources", root / "assets" / "screenshots"
    claim_ids = [f"feature-{fid}-{n}" for n in range(1, len(f.wordings) + 1)]
    shot_name = f"{fid}.{f.screenshot_ext}" if f.screenshot else None

    voice = load_voice(k / "voice.yaml")
    unknown = [a for a in f.audiences if a not in load_audiences(k / "audiences.yaml")]
    if unknown:
        raise ValueError(f"audiences: unknown reader {', '.join(unknown)}")
    for field, texts in (("name", [f.name]), ("does", [f.does]), ("pain", [f.pain]), ("wordings", f.wordings), ("caption", [f.caption or ""])):
        for t in texts:
            if SENSITIVE.search(t):
                raise ValueError(f"{field}: sensitive topic (crashes, deaths, injuries, layoffs, bankruptcies, enforcement, politics); add this one by hand")
    for w in f.wordings:  # claims.yaml wordings skip the customer-voice and product-name checks in validate, so run them here
        bad = [*_banned_words(w, voice), *_retired_names(w, voice), *_competitor_names(w, voice),
               *_customer_voice(w), *_unknown_products(w, voice)]
        if bad:
            raise ValueError(f"wordings: {bad[0].message}: {w!r}")
    if f.screenshot is not None:
        try:
            Image.open(io.BytesIO(f.screenshot)).verify()
        except Exception as e:
            raise ValueError("screenshot: not a readable image") from e
    claims = load_claims(k / "claims.yaml", root=root)
    features = load_features(k / "features.yaml")
    if any(x.label.lower() == f.name.lower() for x in features.values()):
        raise ValueError(f"name: a feature called {f.name!r} already exists")
    if fid in features or any(c in claims for c in claim_ids):
        raise ValueError(f"name: a feature with id {fid!r} already exists")
    if any(b.tag == f"evergreen-{fid}" for b in load_bridges(k / "bridge_map.yaml")):
        raise ValueError(f"name: a bridge for evergreen-{fid} already exists")
    if shot_name and (shots / shot_name).exists():
        raise ValueError(f"screenshot: {shot_name} already exists in assets/screenshots")

    had = set(sources.glob(f"{fid}_{today}.*"))
    try:
        snap = snapshot(fid, f.url, out=sources, today=today)
    except Exception as e:
        for p in set(sources.glob(f"{fid}_{today}.*")) - had:  # only files this call made; FileExistsError made none
            p.unlink()
        raise ValueError(f"url: could not snapshot {f.url}: {e}") from e

    names = ("claims", "features", "bridge_map", "screenshot_captions")
    files = {k / f"{n}.yaml": None for n in names} | {k / "fact_sheet.md": None}
    # shortcut: no lock, the app is local and single-user; two saves at once could interleave. Add a file lock if it is ever shared.
    try:
        files = {p: p.read_bytes() for p in files}
        if shot_name:
            shots.mkdir(parents=True, exist_ok=True)
            (shots / shot_name).write_bytes(f.screenshot)
        snap_rel = snap.relative_to(root).as_posix()
        _append(k / "claims.yaml", "".join(_block(dict(
            id=cid, type="feature", value=f.does, phrasings=[w], source_url=f.url, source_snapshot=snap_rel,
            checked=today, requires_approval=False, verified_by=f.verified_by)) for cid, w in zip(claim_ids, f.wordings)))
        _append(k / "features.yaml", _block(dict(
            id=fid, label=f.name, hemut_feature=f.does, claim_ids=claim_ids,
            screenshots=[dict(file=shot_name, on_screen=f.caption)] if shot_name else [])))
        _append(k / "bridge_map.yaml", _block(dict(
            tag=f"evergreen-{fid}", pain=f.pain, hemut_feature=f.does, claim_ids=claim_ids, feature=fid, audiences=f.audiences)))
        if shot_name:
            _append(k / "screenshot_captions.yaml", "\n" + yaml.safe_dump({shot_name: f.caption}, allow_unicode=True))
        new_claims = load_claims(k / "claims.yaml", root=root)
        (k / "fact_sheet.md").write_text(render_fact_sheet(new_claims), encoding="utf-8", newline="\n")
        feature = load_features(k / "features.yaml").get(fid)
        load_audiences(k / "audiences.yaml")
        captions = load_captions(k / "screenshot_captions.yaml")
        bridged = any(b.tag == f"evergreen-{fid}" for b in load_bridges(k / "bridge_map.yaml"))
        if not (feature and bridged and all(c in new_claims for c in claim_ids) and (not shot_name or shot_name in captions)):
            raise ValueError("name: the new feature did not load back from the knowledge files")
    except Exception as e:
        for p, data in files.items():
            if data is not None:
                p.write_bytes(data)
        for p in sources.glob(f"{fid}_{today}.*"):
            p.unlink()
        if shot_name:
            (shots / shot_name).unlink(missing_ok=True)
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"{e}") from e
    changed = [p for p in files if p.name != "screenshot_captions.yaml" or shot_name] + sorted(sources.glob(f"{fid}_{today}.*"))
    return fid, [p.relative_to(root) for p in changed]
