"""The real knowledge/ files load, fit together, and fact_sheet.md is exactly what claims.yaml renders to."""
from knowledge.build_fact_sheet import OUT, render
from knowledge.loader import load_bridges, load_claims, load_seasons, load_voice


def test_real_claims_load():
    assert load_claims()


def test_real_voice_loads():
    voice = load_voice()
    assert not set(voice.allowed_product_names) & set(voice.retired_names)


def test_fact_sheet_is_fresh():
    assert OUT.read_text(encoding="utf-8") == render(load_claims()), (
        "fact_sheet.md is stale: run python -m knowledge.build_fact_sheet"
    )


def test_every_bridge_claim_exists():
    claims = load_claims()
    missing = {(b.tag, i) for b in load_bridges() for i in b.claim_ids if i not in claims}
    assert not missing, f"bridge_map.yaml uses claim ids not in claims.yaml: {sorted(missing)}"


def test_every_season_has_a_bridge_and_a_unique_id():
    seasons = load_seasons()
    assert len({s.id for s in seasons}) == len(seasons)
    tags = {b.tag for b in load_bridges()}
    assert not {s.id for s in seasons} - tags, "a season with no bridge can never become a Brief"


def test_bridge_text_has_no_digits_or_quotes():
    # research/ rule: bridge text carries no numbers and no quoted speech; facts live in claim_ids
    bad = [(b.tag, field, text) for b in load_bridges() for field, text in (("pain", b.pain), ("hemut_feature", b.hemut_feature))
           if any(c.isdigit() or c in '"“”' for c in text)]
    assert not bad, f"bridge_map.yaml text with a digit or quotation mark: {bad}"
