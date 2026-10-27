"""Mode B with fixed dates and the frozen trend fixture: season windows, trend filtering, rotation, run_week. No network."""
import datetime
import json
from pathlib import Path

import pytest

from test_generate import ANGLES, GOOD, N_ANGLES, FakeClient

from brief_sources.seasonal import active_seasons, window
from brief_sources.trends.fixture import FixtureSource
from modes.scheduled import run_week
from planner import plan_week
from schemas import BridgeEntry, SeasonWindow

D = datetime.date


def season(id_, start, end, lead_days=0, verified_by=None):
    return SeasonWindow(id=id_, name=id_, pain="p", start=start, end=end, lead_days=lead_days,
                        source_url="https://example.com", checked=D(2026, 10, 24), verified_by=verified_by)


def bridge(tag, pain="p"):
    return BridgeEntry(tag=tag, pain=pain, hemut_feature="f", claim_ids=["hemi-desk-detention"])


def tags(plan):
    return [p.brief.origin_ref for p in plan]


def test_season_wraps_past_dec_31():
    winter = season("winter", "12-01", "02-28")
    assert window(winter, D(2026, 12, 20)) == (D(2026, 12, 1), D(2027, 2, 28))
    assert window(winter, D(2027, 2, 10)) == (D(2026, 12, 1), D(2027, 2, 28))  # last year's occurrence
    assert window(winter, D(2027, 3, 1)) is None and window(winter, D(2026, 11, 30)) is None


def test_lead_days_reach_back_across_new_year():
    q4 = season("ifta-q4", "01-01", "01-31", lead_days=7)
    assert window(q4, D(2026, 12, 25)) == (D(2027, 1, 1), D(2027, 1, 31))
    assert window(q4, D(2026, 12, 24)) is None
    (item,) = active_seasons(D(2026, 12, 25), [q4], [bridge("ifta-q4")])
    assert item.brief.origin == "seasonal" and "starts Jan 01, 7 days out" in item.reason


def test_feb_29_window_in_a_non_leap_year():
    assert window(season("leap", "02-01", "02-29"), D(2027, 2, 28)) == (D(2027, 2, 1), D(2027, 2, 28))


def test_unverified_season_still_briefs_but_says_so():
    s = season("ifta-q3", "10-01", "10-31")
    (item,) = active_seasons(D(2026, 10, 15), [s], [bridge("ifta-q3")])
    assert "unverified" in item.reason
    (item,) = active_seasons(D(2026, 10, 15), [s.model_copy(update={"verified_by": "Bryan"})], [bridge("ifta-q3")])
    assert "verified by Bryan" in item.reason


def test_demo_week_plan():
    skipped = []
    plan = plan_week(D(2026, 10, 31), skipped=skipped)
    assert tags(plan) == ["ifta-q3", "hurricane-season", "detention", "evergreen-pricing", "evergreen-rate-cons"]
    assert [p.brief.origin for p in plan[:3]] == ["seasonal", "seasonal", "trend"]  # active seasons first: the boost
    assert all("dates verified by" in p.reason for p in plan[:2])
    assert "evergreen-switching: no slot left this week" in skipped
    assert any(s.startswith("Trend check-call-overload: expired") for s in skipped)
    assert any(s.startswith("Trend truck-parking: no bridge") for s in skipped)
    assert any(s.startswith("Trend english-proficiency-enforcement: sensitive") for s in skipped)


def test_sensitive_card_never_briefs_even_with_a_bridge():
    plan = plan_week(D(2026, 10, 31), seasons=[], bridges=[bridge("english-proficiency-enforcement"), bridge("detention")])
    assert tags(plan) == ["detention"]


def test_fixture_cards_reference_real_items():
    items, cards = FixtureSource().fetch()
    assert {c.sensitivity for c in cards} == {"low", "high"} and len(cards) == 4 and items


def test_every_new_trend_tag_becomes_a_brief():
    fixture = FixtureSource(Path(__file__).parent / "fixtures" / "trends_bridges_2026-10-26.yaml")
    _, cards = fixture.fetch()
    plan = plan_week(D(2026, 10, 31), seasons=[], trends=fixture, slots=len(cards))
    assert sorted(tags(plan)) == sorted(c.tag for c in cards)
    assert {p.brief.origin for p in plan} == {"trend"}


def test_repeated_angle_skipped_and_tag_rotates():
    last_week = plan_week(D(2026, 10, 24))
    skipped = []
    this_week = plan_week(D(2026, 10, 31), previous=last_week, skipped=skipped)
    ifta = [p for p in this_week if p.brief.origin_ref == "ifta-q3"]
    assert len(ifta) == 1 and ifta[0].brief.pain != last_week[0].brief.pain  # IFTA's second angle this week
    assert "detention" not in tags(this_week)  # only one angle, used last week
    assert any(s.startswith("detention: angle used last week") for s in skipped)


def test_run_week_runs_each_brief(tmp_path):
    plan = plan_week(D(2026, 10, 31))[:1]
    client = FakeClient(ANGLES, GOOD)
    (result,) = list(run_week(D(2026, 10, 31), plan, client=client, out_root=tmp_path))
    assert result.status == "ok" and len(client.calls) == 1 + N_ANGLES
    meta = json.loads((Path(result.run_dir) / "meta.json").read_text(encoding="utf-8"))
    assert meta["mode"] == "B" and meta["brief_origin"] == "seasonal" and "normalize.txt" not in meta["prompt_versions"]


def test_week_failure_keeps_earlier_results(tmp_path):
    plan = plan_week(D(2026, 10, 31))[:2]
    week = run_week(D(2026, 10, 31), plan, client=FakeClient(ANGLES, GOOD, GOOD, GOOD, RuntimeError("boom")), out_root=tmp_path)
    assert next(week).status == "ok"  # the first Brief is handed back before the second one fails
    with pytest.raises(RuntimeError):
        next(week)


def test_overflow_is_reported_not_silent():
    skipped = []
    plan = plan_week(D(2027, 1, 10), slots=4, skipped=skipped)  # IFTA Q4, winter and 3 pillars: 5 tags for 4 slots
    assert tags(plan) == ["ifta-q4", "winter-weather", "evergreen-pricing", "evergreen-rate-cons"]
    assert "evergreen-switching: no slot left this week" in skipped
    assert not any(s.startswith(("ifta-q4", "winter-weather")) for s in skipped)  # a tag's second angle is not "left out"
