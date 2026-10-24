"""The real knowledge/ files load, and fact_sheet.md is exactly what claims.yaml renders to."""
from knowledge.build_fact_sheet import OUT, render
from knowledge.loader import load_claims, load_voice


def test_real_claims_load():
    assert load_claims()


def test_real_voice_loads():
    voice = load_voice()
    assert not set(voice.allowed_product_names) & set(voice.retired_names)


def test_fact_sheet_is_fresh():
    assert OUT.read_text(encoding="utf-8") == render(load_claims()), (
        "fact_sheet.md is stale: run python -m knowledge.build_fact_sheet"
    )
