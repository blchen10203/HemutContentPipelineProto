"""Mode B with fixed dates: season windows, rotation, personas, run_week. No network."""
import datetime
import json
from pathlib import Path

import pytest

from test_generate import ANGLES, GOOD, N_ANGLES, FakeClient

from brief_sources.seasonal import active_seasons, window
from modes.scheduled import run_week
from planner import plan_week
from schemas import BridgeEntry, SeasonWindow

D = datetime.date


def season(id_, start, end, lead_days=0, verified_by=None):
    return SeasonWindow(id=id_, name=id_, start=start, end=end, lead_days=lead_days,
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
    ((matched, reason),) = active_seasons(D(2026, 12, 25), [q4], [bridge("ifta-q4")])
    assert matched.tag == "ifta-q4" and "starts Jan 01, 7 days out" in reason


def test_feb_29_window_in_a_non_leap_year():
    assert window(season("leap", "02-01", "02-29"), D(2027, 2, 28)) == (D(2027, 2, 1), D(2027, 2, 28))


def test_unverified_season_still_briefs_but_says_so():
    s = season("ifta-q3", "10-01", "10-31")
    ((_, reason),) = active_seasons(D(2026, 10, 15), [s], [bridge("ifta-q3")])
    assert "unverified" in reason
    ((_, reason),) = active_seasons(D(2026, 10, 15), [s.model_copy(update={"verified_by": "Bryan"})], [bridge("ifta-q3")])
    assert "verified by Bryan" in reason


def test_demo_week_plan():
    skipped = []
    plan = plan_week(D(2026, 10, 31), skipped=skipped)
    assert tags(plan) == ["ifta-q3", "hurricane-season", "evergreen-pricing", "evergreen-rate-cons", "evergreen-switching"]
    assert [p.brief.origin for p in plan] == ["seasonal"] * 2 + ["evergreen"] * 3  # active seasons first: the boost
    assert all("dates verified by" in p.reason for p in plan[:2])
    assert skipped == []


def test_consecutive_weeks_rotate_angles():
    pains = [{p.brief.origin_ref: p.brief.pain for p in plan_week(D(2026, 10, 17) + datetime.timedelta(weeks=n))} for n in range(3)]
    for tag in ("ifta-q3", "hurricane-season"):  # two angles each: they alternate week to week
        assert pains[0][tag] != pains[1][tag] and pains[0][tag] == pains[2][tag]


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


def test_overlapping_seasons_never_repeat_a_feature():
    skipped = []
    plan = plan_week(D(2026, 11, 21), skipped=skipped)  # winter's lead overlaps the end of hurricane season
    assert {"winter-weather", "hurricane-season"} <= set(tags(plan))
    assert len({p.brief.hemut_feature for p in plan}) == len(plan)
    assert any(s.startswith("hurricane-season: same feature already in this week's plan") for s in skipped)


def test_demo_week_personas():
    plan = plan_week(D(2026, 10, 31))
    assert [p.brief.audience_id for p in plan] == ["back-office", "dispatcher", "fleet-owner", "back-office", "fleet-owner"]
    assert plan[0].reason.endswith("Reader: Back-office and billing lead") and plan[0].brief.audience == "Back-office and billing lead"


def test_personas_spread_across_slots():
    one_option = BridgeEntry(tag="evergreen-a", pain="pa", hemut_feature="fa", claim_ids=[], audiences=["dispatcher"])
    two_options = BridgeEntry(tag="evergreen-b", pain="pb", hemut_feature="fb", claim_ids=[], audiences=["dispatcher", "back-office"])
    any_persona = BridgeEntry(tag="evergreen-c", pain="pc", hemut_feature="fc", claim_ids=[])
    plan = plan_week(D(2026, 10, 31), seasons=[], bridges=[two_options, one_option, any_persona])
    # the single-option slot picks first, so the two-option slot moves aside, and the open slot takes an unused persona
    assert [p.brief.audience_id for p in plan] == ["back-office", "dispatcher", "fleet-owner"]


def test_overflow_is_reported_not_silent():
    skipped = []
    plan = plan_week(D(2027, 1, 10), slots=4, skipped=skipped)  # IFTA Q4, winter and 3 pillars: 5 tags for 4 slots
    assert tags(plan) == ["ifta-q4", "winter-weather", "evergreen-pricing", "evergreen-rate-cons"]
    assert "evergreen-switching: no slot left this week" in skipped
    assert not any(s.startswith(("ifta-q4", "winter-weather")) for s in skipped)  # a tag's second angle is not "left out"
