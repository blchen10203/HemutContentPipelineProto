import pytest
import yaml

from knowledge.loader import load_audiences, load_bridges, load_claims, load_features, load_voice


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


@pytest.mark.parametrize("overrides", [
    {"value": 99},  # numeric value, price type
    {"type": "company", "value": 20},  # numeric value, otherwise-allowed type
    {"type": "competitor", "value": "no published prices"},  # non-numeric, but not an allowed type
])
def test_empty_phrasings_rejected(repo, overrides):
    with pytest.raises(ValueError, match="needs at least one phrasing"):
        load(repo, [claim(phrasings=[], **overrides)])


def test_empty_phrasings_allowed_for_record_only_text(repo):
    claims = load(repo, [claim(type="company", value="A customer quote", phrasings=[])])
    assert claims["command-base-price"].phrasings == []


def test_repeated_key_fails(repo):
    path = repo / "knowledge" / "claims.yaml"
    text = yaml.safe_dump([claim(requires_approval=True)])
    path.write_text(text + "  requires_approval: false\n")  # same key again, last would silently win
    with pytest.raises(ValueError, match="duplicate key 'requires_approval'"):
        load_claims(path, root=repo)


@pytest.mark.parametrize("value", [True, False])
def test_boolean_value_fails(repo, value):
    with pytest.raises(ValueError, match="value"):
        load(repo, [claim(value=value)])


def test_unknown_key_fails(repo):
    with pytest.raises(ValueError, match="phrasing"):
        load(repo, [claim(phrasing=["typo of phrasings"])])


def test_empty_voice_fails(tmp_path):
    path = tmp_path / "voice.yaml"
    path.write_text("# nothing yet\n")
    with pytest.raises(ValueError):
        load_voice(path)


PERSONA = {"id": "dispatcher", "label": "Dispatcher", "role": "Runs the board.", "pains": ["Check calls all day"],
           "objections": ["Another screen"], "tone_notes": ["Fast and concrete"]}


@pytest.mark.parametrize("field,text", [
    ("pains", ["Waits 30 days to get paid"]),
    ("objections", ["My people won't learn it"]),
    ("tone_notes", ["Say “no card” up front"]),
    ("role", "Busiest in November"),
])
def test_persona_text_with_numbers_dates_quotes_or_first_person_fails(tmp_path, field, text):
    path = tmp_path / "audiences.yaml"
    path.write_text(yaml.safe_dump([{**PERSONA, field: text}]), encoding="utf-8")
    with pytest.raises(ValueError, match="persona 'dispatcher'"):
        load_audiences(path)


@pytest.mark.parametrize("pain", ["Busy in November", "Customers call us all day", "Detention runs past two hours on 4 loads"])
def test_bridge_text_follows_the_same_rule(tmp_path, pain):
    path = tmp_path / "bridge_map.yaml"
    path.write_text(yaml.safe_dump([{"tag": "detention", "pain": pain, "hemut_feature": "f", "claim_ids": [], "feature": "f"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="bridge 'detention'"):
        load_bridges(path)


def test_duplicate_persona_id_fails(tmp_path):
    path = tmp_path / "audiences.yaml"
    path.write_text(yaml.safe_dump([PERSONA, PERSONA]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate audience id"):
        load_audiences(path)


def test_duplicate_feature_id_fails(tmp_path):
    path = tmp_path / "features.yaml"
    entry = {"id": "ifta", "label": "IFTA", "hemut_feature": "IFTA reports", "claim_ids": []}
    path.write_text(yaml.safe_dump([entry, entry]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate feature id 'ifta'"):
        load_features(path)
