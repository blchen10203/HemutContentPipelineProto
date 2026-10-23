"""Load knowledge/claims.yaml and knowledge/voice.yaml into schemas models. Raises ValueError on anything malformed."""
from pathlib import Path

import yaml
from pydantic import ValidationError

from schemas import Claim, VoiceRules

ROOT = Path(__file__).resolve().parent.parent


def load_claims(path: Path = ROOT / "knowledge" / "claims.yaml", root: Path = ROOT) -> dict[str, Claim]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a list of claims, got {type(raw).__name__}")
    sources = (root / "knowledge" / "sources").resolve()
    claims: dict[str, Claim] = {}
    for i, item in enumerate(raw):
        try:
            claim = Claim.model_validate(item)
        except ValidationError as e:
            raise ValueError(f"{path}: claim #{i}: {e}") from e
        if claim.id in claims:
            raise ValueError(f"{path}: duplicate claim id {claim.id!r}")
        snapshot = (root / claim.source_snapshot).resolve()
        if not (snapshot.is_file() and snapshot.is_relative_to(sources)):
            raise ValueError(f"{path}: claim {claim.id!r}: source_snapshot {claim.source_snapshot!r} is not a file in knowledge/sources")
        claims[claim.id] = claim
    return claims


def load_voice(path: Path = ROOT / "knowledge" / "voice.yaml") -> VoiceRules:
    try:
        return VoiceRules.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValidationError as e:
        raise ValueError(f"{path}: {e}") from e
