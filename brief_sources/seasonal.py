"""Seasonal Brief source: which seasonality.yaml windows are active on a date, matched to their bridge_map.yaml entries.

A window is active from (start - lead_days) through end. start after end means it wraps past Dec 31.
Unverified windows (verified_by: null) still count; their reason says so.
"""
import calendar
import datetime

from schemas import AudienceProfile, Brief, BridgeEntry, SeasonWindow

FORMAT = {"seasonal": "reddit_post", "evergreen": "short_ad"}


def bridge_brief(bridge: BridgeEntry, origin: str, persona: AudienceProfile) -> Brief:
    """The one way a season or pillar becomes a Brief."""
    return Brief(origin=origin, audience=persona.label, audience_id=persona.id, pain=bridge.pain, hemut_feature=bridge.hemut_feature,
                 format=FORMAT[origin], claim_ids=bridge.claim_ids, origin_ref=bridge.tag)


def window(season: SeasonWindow, today: datetime.date) -> tuple[datetime.date, datetime.date] | None:
    """The (start, end) occurrence of the season that is active today, counting lead_days, or None."""
    wraps = season.end < season.start  # MM-DD strings compare in date order
    for year in (today.year - 1, today.year, today.year + 1):  # last year's window can wrap into today; next year's lead can start today
        start, end = _date(year, season.start), _date(year + wraps, season.end)
        if start - datetime.timedelta(days=season.lead_days) <= today <= end:
            return start, end
    return None


def active_seasons(today: datetime.date, seasons: list[SeasonWindow], bridges: list[BridgeEntry]) -> list[tuple[BridgeEntry, str]]:
    """(bridge, reason) for every bridge of every season active today. The planner picks a persona and makes the Brief."""
    out = []
    for season in seasons:
        if not (dates := window(season, today)):
            continue
        start, end = dates
        when = f"in season until {end:%b %d}" if today >= start else f"starts {start:%b %d}, {(start - today).days} days out"
        check = f"dates verified by {season.verified_by}" if season.verified_by else "dates unverified, not yet checked by a human"
        reason = f"Season: {season.name}, {when} ({check}; source {season.source_url})"
        out += [(b, reason) for b in bridges if b.tag == season.id]
    return out


def _date(year: int, month_day: str) -> datetime.date:
    month, day = map(int, month_day.split("-"))
    if (month, day) == (2, 29) and not calendar.isleap(year):
        day = 28  # SeasonWindow allows 02-29; in other years the window ends a day early
    return datetime.date(year, month, day)
