import datetime
import shutil

import httpx
import pytest
from conftest import TINY_PNG
from pydantic import ValidationError

import knowledge.add_feature
from knowledge.add_feature import NewFeature, add_feature
from knowledge.loader import ROOT, load_audiences, load_bridges, load_captions, load_claims, load_features
from planner import plan_week
from schemas import Claim

VALID_CLAIM = dict(id="voice-agents", type="feature", value="Voice agents", phrasings=["Hemi places check calls"],
                   source_url="https://hemut.com/voice-agents", source_snapshot="knowledge/sources/x.txt",
                   checked="2026-11-06", requires_approval=False)

GOOD = dict(name="Voice agents for check calls", does="Phone agents that place driver check calls",
            url="https://hemut.com/voice-agents", wordings=["Hemi places the driver check calls for you", " ", ""],
            verified_by="Jane Doe (Product Manager)", pain="Dispatchers lose hours chasing drivers for check calls",
            audiences=["dispatcher"])


def nf(**over): return NewFeature(**(GOOD | over))


def test_good_feature_strips_and_drops_blank_wordings():
    f = nf()
    assert f.id == "voice-agents-for-check-calls" and f.wordings == ["Hemi places the driver check calls for you"]


@pytest.mark.parametrize("over, field", [
    ({"url": "http://hemut.com/x"}, "url"), ({"url": "https://hemut.com.evil.io/x"}, "url"),
    ({"url": "https://nothemut.com/x"}, "url"), ({"wordings": ["", " "]}, "wordings"),
    ({"wordings": ["a", "b", "c", "d"]}, "wordings"), ({"verified_by": "Jane Doe"}, "verified_by"),
    ({"pain": "Dispatchers lose 3 hours"}, "pain"), ({"audiences": []}, "audiences"),
    ({"name": "!!!"}, "name"), ({"screenshot": b"x", "screenshot_ext": "png"}, "caption"),
    ({"caption": "Shows the call log"}, "screenshot"),
])
def test_bad_fields_are_rejected(over, field):
    with pytest.raises(ValidationError, match=field):
        nf(**over)


def test_subdomain_url_is_allowed():
    assert nf(url="https://command.hemut.com/x").url == "https://command.hemut.com/x"


def test_claim_takes_verified_by():
    assert Claim.model_validate({**VALID_CLAIM, "verified_by": "Jane Doe (PM)"}).verified_by == "Jane Doe (PM)"


DAY = datetime.date(2026, 11, 6)


def snapshot_bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for d in ("knowledge", "assets") for p in (root / d).rglob("*") if p.is_file()}


@pytest.fixture
def kb(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "knowledge", tmp_path / "knowledge")
    (tmp_path / "assets" / "screenshots").mkdir(parents=True)

    def fake(name, url, *, out, today, **_):
        path = out / f"{name}_{today}.txt"
        path.write_text("<page>", encoding="utf-8")
        return path
    monkeypatch.setattr(knowledge.add_feature, "snapshot", fake)
    return tmp_path


def test_happy_path_goes_live(kb):
    fid, _ = add_feature(nf(screenshot=TINY_PNG, screenshot_ext="png", caption="Agents place calls for you"), root=kb, today=DAY)
    k = kb / "knowledge"
    claims = load_claims(k / "claims.yaml", root=kb)
    assert claims[f"feature-{fid}-1"].verified_by == "Jane Doe (Product Manager)"
    assert claims[f"feature-{fid}-1"].source_snapshot == f"knowledge/sources/{fid}_2026-11-06.txt"
    assert load_features(k / "features.yaml")[fid].screenshots[0].file == f"{fid}.png"
    assert any(b.tag == f"evergreen-{fid}" for b in load_bridges(k / "bridge_map.yaml"))
    assert load_captions(k / "screenshot_captions.yaml")[f"{fid}.png"] == "Agents place calls for you"
    assert f"feature-{fid}-1" in (k / "fact_sheet.md").read_text(encoding="utf-8")
    picked = {i.brief.feature_id for w in range(52) for i in plan_week(DAY + datetime.timedelta(weeks=w), seasons=[],
              bridges=load_bridges(k / "bridge_map.yaml"), audiences=load_audiences(k / "audiences.yaml"))}
    assert fid in picked


def test_yaml_special_characters_round_trip(kb):
    text = 'Hemi: books loads # fast - "quoted" ’smart’ café'
    fid, _ = add_feature(nf(wordings=[text]), root=kb, today=DAY)
    assert load_claims(kb / "knowledge" / "claims.yaml", root=kb)[f"feature-{fid}-1"].phrasings == [text]


@pytest.mark.parametrize("over", [{"wordings": ["Guaranteed on-time loads"]}, {"wordings": ["Built on Hemut Core"]},
                                  {"audiences": ["no-such-reader"]}])
def test_voice_and_audience_checks_write_nothing(kb, over):
    before = snapshot_bytes(kb)
    with pytest.raises(ValueError):
        add_feature(nf(**over), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before


def test_duplicate_name_is_rejected(kb):
    add_feature(nf(), root=kb, today=DAY)
    with pytest.raises(ValueError, match="name"):
        add_feature(nf(), root=kb, today=DAY + datetime.timedelta(days=1))


def test_failure_after_writing_restores_every_file(kb, monkeypatch):
    before = snapshot_bytes(kb)
    monkeypatch.setattr(knowledge.add_feature, "render_fact_sheet", lambda claims: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(ValueError, match="boom"):
        add_feature(nf(screenshot=TINY_PNG, screenshot_ext="png", caption="Agents place calls for you"), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before  # knowledge files, sources and screenshots all as they were


def test_fetch_failure_writes_nothing(kb, monkeypatch):
    before = snapshot_bytes(kb)

    def fail(*a, **k): raise httpx.ConnectTimeout("timed out")
    monkeypatch.setattr(knowledge.add_feature, "snapshot", fail)
    with pytest.raises(ValueError, match="url"):
        add_feature(nf(), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before


def test_header_comments_survive(kb):
    first = (kb / "knowledge" / "features.yaml").read_text(encoding="utf-8").splitlines()[0]
    add_feature(nf(), root=kb, today=DAY)
    assert (kb / "knowledge" / "features.yaml").read_text(encoding="utf-8").splitlines()[0] == first


@pytest.mark.parametrize("over", [
    {"wordings": ["I switched to Hemut and stopped chasing check calls"]},
    {"wordings": ["Hemut Voice places the check calls for you"]},
    {"wordings": ["Hemut beats Turvo at check calls"]},
    {"name": "Accident register for DOT audits"},
    {"pain": "Dispatchers dread layoffs and chasing drivers"},
    {"name": "Detention tracking"},
])
def test_wording_and_name_rejections_write_nothing(kb, over):
    before = snapshot_bytes(kb)
    with pytest.raises(ValueError):
        add_feature(nf(**over), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before


def test_sensitive_and_duplicate_label_messages(kb):
    with pytest.raises(ValueError, match="name: sensitive topic"):
        add_feature(nf(name="Accident register for DOT audits"), root=kb, today=DAY)
    with pytest.raises(ValueError, match="^name:"):
        add_feature(nf(name="detention TRACKING"), root=kb, today=DAY)


@pytest.mark.parametrize("over, field", [({"does": ""}, "does"), ({"pain": "  "}, "pain"), ({"name": ""}, "name"),
                                         ({"verified_by": "Jane ( )"}, "verified_by")])
def test_blank_required_fields_rejected(over, field):
    with pytest.raises(ValidationError, match=field):
        nf(**over)


def test_snapshot_failure_cleans_up_what_it_created(kb, monkeypatch):
    before = snapshot_bytes(kb)

    def half(name, url, *, out, today, **_):
        (out / f"{name}_{today}.html").write_text("<page>", encoding="utf-8")
        raise RuntimeError("disk full")
    monkeypatch.setattr(knowledge.add_feature, "snapshot", half)
    with pytest.raises(ValueError, match="^url:"):
        add_feature(nf(), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before


def test_returns_files_to_commit(kb):
    fid, changed = add_feature(nf(screenshot=TINY_PNG, screenshot_ext="png", caption="Agents place calls"), root=kb, today=DAY)
    got = {p.as_posix() for p in changed}
    assert {"knowledge/claims.yaml", "knowledge/features.yaml", "knowledge/bridge_map.yaml", "knowledge/fact_sheet.md",
            "knowledge/screenshot_captions.yaml", f"knowledge/sources/{fid}_2026-11-06.txt"} == got


def test_unreadable_screenshot_rejected(kb):
    before = snapshot_bytes(kb)
    with pytest.raises(ValueError, match="screenshot: not a readable image"):
        add_feature(nf(screenshot=b"not an image", screenshot_ext="png", caption="x"), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before


def test_rollback_cause_is_not_itself(kb, monkeypatch):
    monkeypatch.setattr(knowledge.add_feature, "render_fact_sheet", lambda claims: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(ValueError) as ei:
        add_feature(nf(), root=kb, today=DAY)
    assert ei.value.__cause__ is not ei.value
