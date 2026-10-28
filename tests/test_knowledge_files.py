"""The real knowledge/ files load, fit together, and fact_sheet.md is exactly what claims.yaml renders to."""
import re

from knowledge.build_fact_sheet import OUT, render
from knowledge.loader import load_audiences, load_bridges, load_claims, load_seasons, load_voice
from validate import _banned_words, _competitor_names


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


def test_no_claim_wording_contains_a_banned_word():
    # validate() checks claim wordings too, so one banned word here would fail every draft that uses the claim
    voice = load_voice()
    bad = {(c.id, v.span) for c in load_claims().values() for p in c.phrasings for v in _banned_words(p, voice)}
    assert not bad, f"claims.yaml wordings with a banned word from voice.yaml: {sorted(bad)}"


# Phrasings that state the value another way: "Over 30 trucks" (value 31), "about five minutes" (value 5).
VALUE_IN_WORDS = {"enterprise-threshold", "setup-signup-minutes"}


def test_numeric_claim_wordings_state_their_value():
    # Only phrasings reach copy, never value: a price changed in one place but not the other would ship the old price
    wrong = []
    for c in load_claims().values():
        if isinstance(c.value, (int, float)) and c.id not in VALUE_IN_WORDS:
            number = str(int(c.value)) if float(c.value).is_integer() else str(c.value)
            wrong += [(c.id, c.value, p) for p in c.phrasings
                      if not re.search(rf"(?<![\d.]){re.escape(number)}(?![\d]|\.\d)", p.replace(",", ""))]
    assert not wrong, f"claims.yaml wordings that do not state the claim's value: {wrong}"


def test_every_bridge_persona_exists():
    audiences = load_audiences()
    missing = {(b.tag, a) for b in load_bridges() for a in b.audiences if a not in audiences}
    assert not missing, f"bridge_map.yaml uses persona ids not in audiences.yaml: {sorted(missing)}"


def test_only_competitor_claims_name_a_competitor():
    # The validator rejects any wording that names a competitor: competitor claims must name one (so they stay
    # background), and any other claim that does could never be used. company-not-loadstop is background by design.
    voice = load_voice()
    wrong = {
        (c.id, p) for c in load_claims().values() if c.id != "company-not-loadstop"
        for p in c.phrasings if (c.type == "competitor") != bool(_competitor_names(p, voice))
    }
    assert not wrong, f"claim wordings that should (competitor) or must not (others) name a voice.yaml competitor: {sorted(wrong)}"


def test_allowed_competitor_phrases_are_claim_wordings():
    # Each entry switches off the competitor check for its text, so only exact non-competitor claim wordings belong
    wordings = {p for c in load_claims().values() if c.type != "competitor" for p in c.phrasings}
    extra = set(load_voice().allowed_competitor_phrases) - wordings
    assert not extra, f"allowed_competitor_phrases not an exact non-competitor claim wording: {sorted(extra)}"
