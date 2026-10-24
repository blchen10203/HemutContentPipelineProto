"""Weekly content plan for Mode B: active seasons first (the boost), then live trend cards, then evergreen pillars.

One angle per tag per week. An angle (tag + pain) used in the previous plan is skipped, so a tag with two bridge
entries rotates between them week to week. Trends need a bridge, an unexpired card and low sensitivity.
"""
import datetime

from brief_sources.seasonal import active_seasons, bridge_brief
from brief_sources.trends.base import TrendSource
from brief_sources.trends.fixture import FixtureSource
from knowledge.loader import load_bridges, load_seasons
from schemas import BridgeEntry, PlanItem, SeasonWindow

SLOTS = 5


def plan_week(
    today: datetime.date,
    *,
    seasons: list[SeasonWindow] | None = None,
    bridges: list[BridgeEntry] | None = None,
    trends: TrendSource | None = None,
    previous: list[PlanItem] = (),
    slots: int = SLOTS,
    skipped: list[str] | None = None,  # if given, gets one plain-English line per thing left out, for a human
) -> list[PlanItem]:
    seasons = load_seasons() if seasons is None else seasons
    bridges = load_bridges() if bridges is None else bridges
    items, cards = (trends or FixtureSource()).fetch()
    titles = {i.id: i.title for i in items}
    skipped = [] if skipped is None else skipped

    candidates = active_seasons(today, seasons, bridges)
    for card in sorted(cards, key=lambda c: len(c.items), reverse=True):  # most-discussed first
        matches = [b for b in bridges if b.tag == card.tag]
        if card.sensitivity == "high":
            skipped.append(f"Trend {card.tag}: sensitive, needs a human ({card.sensitivity_reason or 'no reason given'})")
        elif card.expires_at < today:
            skipped.append(f"Trend {card.tag}: expired {card.expires_at:%b %d}")
        elif not matches:
            skipped.append(f"Trend {card.tag}: no bridge to a Hemut feature")
        else:
            reason = f"Trend: {titles[card.items[0]]} ({len(card.items)} items, card good until {card.expires_at:%b %d})"
            candidates += [PlanItem(brief=bridge_brief(b, "trend"), reason=reason) for b in matches]
    candidates += [
        PlanItem(brief=bridge_brief(b, "evergreen"), reason=f"Evergreen pillar: {b.tag.removeprefix('evergreen-')}")
        for b in bridges if b.tag.startswith("evergreen-")
    ]

    used = {_angle(p) for p in previous}
    plan, tags = [], set()
    for item in candidates:
        tag = item.brief.origin_ref
        if _angle(item) in used:
            skipped.append(f"{tag}: angle used last week ({item.brief.pain})")
        elif tag in tags:
            continue  # this tag's other angle is already in the plan
        elif len(plan) >= slots:
            skipped.append(f"{tag}: no slot left this week")
        else:
            plan.append(item)
            tags.add(tag)
    return plan


def _angle(item: PlanItem) -> tuple[str | None, str]:
    return item.brief.origin_ref, item.brief.pain
