import pytest
import yaml

from knowledge.loader import load_claims, load_voice


def claim(**overrides):
    c = {
        "id": "command-base-price",
        "type": "price",
        "value": 99,
        "unit": "USD/month",
        "phrasings": ["Command starts at $99 a month"],
        "context": "3 trucks included",
        "source_url": "https://hemut.com/pricing",
        "source_snapshot": "knowledge/sources/pricing_2026-10-23.txt",
        "checked": "2026-10-23",
        "requires_approval": False,
    }
    c.update(overrides)
    return {k: v for k, v in c.items() if v is not None}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "knowledge" / "sources").mkdir(parents=True)
    (tmp_path / "knowledge" / "sources" / "pricing_2026-10-23.txt").write_text("Command $99/mo")
    return tmp_path


def load(repo, claims):
    path = repo / "knowledge" / "claims.yaml"
    path.write_text(yaml.safe_dump(claims))
    return load_claims(path, root=repo)


def test_valid_claims_load(repo):
    claims = load(repo, [claim(), claim(id="command-trial-days", value=30)])
    assert claims["command-base-price"].value == 99
    assert str(claims["command-base-price"].checked) == "2026-10-23"


def test_duplicate_id_fails(repo):
    with pytest.raises(ValueError, match="duplicate claim id 'command-base-price'"):
        load(repo, [claim(), claim()])


@pytest.mark.parametrize("missing", ["source_url", "source_snapshot"])
def test_missing_source_fails(repo, missing):
    with pytest.raises(ValueError, match=missing):
        load(repo, [claim(**{missing: None})])


@pytest.mark.parametrize("snapshot", [
    "knowledge/sources/pricing_2099-01-01.txt",  # does not exist
    "knowledge/claims.yaml",  # exists, but is not a snapshot
])
def test_bad_snapshot_path_fails(repo, snapshot):
    with pytest.raises(ValueError, match="is not a file in knowledge/sources"):
        load(repo, [claim(source_snapshot=snapshot)])


def test_unknown_key_fails(repo):
    with pytest.raises(ValueError, match="phrasing"):
        load(repo, [claim(phrasing=["typo of phrasings"])])


def test_empty_voice_fails(tmp_path):
    path = tmp_path / "voice.yaml"
    path.write_text("# nothing yet\n")
    with pytest.raises(ValueError):
        load_voice(path)
