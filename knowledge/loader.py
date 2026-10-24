"""Load knowledge/*.yaml (claims, voice, seasonality, bridge map) into schemas models. Raises ValueError on anything malformed."""
from pathlib import Path

import yaml
from pydantic import ValidationError

from schemas import BridgeEntry, Claim, SeasonWindow, VoiceRules

ROOT = Path(__file__).resolve().parent.parent


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects a key repeated in one mapping; plain PyYAML silently keeps the last one."""


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _read_yaml(path: Path):
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as e:
        raise ValueError(f"{path}: {e}") from e


def load_claims(path: Path = ROOT / "knowledge" / "claims.yaml", root: Path = ROOT) -> dict[str, Claim]:
    raw = _read_yaml(path) or []
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
        return VoiceRules.model_validate(_read_yaml(path))
    except ValidationError as e:
        raise ValueError(f"{path}: {e}") from e


def load_seasons(path: Path = ROOT / "knowledge" / "seasonality.yaml") -> list[SeasonWindow]:
    return _load_list(path, SeasonWindow)


def load_bridges(path: Path = ROOT / "knowledge" / "bridge_map.yaml") -> list[BridgeEntry]:
    return _load_list(path, BridgeEntry)


def _load_list(path: Path, model):
    raw = _read_yaml(path) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a list, got {type(raw).__name__}")
    try:
        return [model.model_validate(item) for item in raw]
    except ValidationError as e:
        raise ValueError(f"{path}: {e}") from e
