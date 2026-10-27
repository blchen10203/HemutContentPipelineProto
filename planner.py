"""Weekly content plan for Mode B: active seasons first (the boost), then live trend cards, then evergreen pillars.

One angle per tag per week. A tag with several bridge entries rotates through them by week number, so consecutive
weeks lead with different angles without any stored history. Two tags never sell the same hemut_feature in one week. Trends need a bridge, an unexpired card and low sensitivity.
Once the slots are filled, each gets a reader persona from its bridge's audiences, spread so a week repeats one as little as it can.
"""
import datetime

from brief_sources.seasonal import active_seasons, bridge_brief
from brief_sources.trends.base import TrendSource
from brief_sources.trends.fixture import FixtureSource
from knowledge.loader import load_audiences, load_bridges, load_seasons
from schemas import AudienceProfile, BridgeEntry, PlanItem, SeasonWindow

SLOTS = 5


def plan_week(
    today: datetime.date,
    *,
    seasons: list[SeasonWindow] | None = None,
    bridges: list[BridgeEntry] | None = None,
    audiences: dict[str, AudienceProfile] | None = None,
    trends: TrendSource | None = None,
    slots: int = SLOTS,
    skipped: list[str] | None = None,  # if given, gets one plain-English line per thing left out, for a human
) -> list[PlanItem]:
    seasons = load_seasons() if seasons is None else seasons
    bridges = load_bridges() if bridges is None else bridges
    audiences = load_audiences() if audiences is None else audiences
    items, cards = (trends or FixtureSource()).fetch()
    titles = {i.id: i.title for i in items}
    skipped = [] if skipped is None else skipped

    candidates = [(b, "seasonal", reason) for b, reason in active_seasons(today, seasons, bridges)]
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
            candidates += [(b, "trend", reason) for b in matches]
    candidates += [(b, "evergreen", f"Evergreen pillar: {b.tag.removeprefix('evergreen-')}")
                   for b in bridges if b.tag.startswith("evergreen-")]

    week = (today.toordinal() - 1) // 7  # weeks since a Monday, unbroken across years (ISO week 53 would repeat)
    by_tag: dict[str, list] = {}
    for c in candidates:
        by_tag.setdefault(c[0].tag, []).append(c)
    candidates = [c for group in by_tag.values() for c in group[week % len(group):] + group[:week % len(group)]]

    picked, tags, features = [], set(), set()
    for bridge, origin, reason in candidates:
        tag = bridge.tag
        if tag in tags:
            continue  # this tag's other angle is already in the plan
        elif bridge.hemut_feature in features:
            skipped.append(f"{tag}: same feature already in this week's plan ({bridge.hemut_feature})")
        elif len(picked) >= slots:
            skipped.append(f"{tag}: no slot left this week")
        else:
            picked.append((bridge, origin, reason))
            tags.add(tag)
            features.add(bridge.hemut_feature)

    personas = _personas([b for b, _, _ in picked], audiences)
    return [PlanItem(brief=bridge_brief(b, origin, persona), reason=f"{reason} · Reader: {persona.label}")
            for (b, origin, reason), persona in zip(picked, personas)]


def _personas(bridges: list[BridgeEntry], audiences: dict[str, AudienceProfile]) -> list[AudienceProfile]:
    """One persona per slot: slots with the fewest options choose first, each taking its least-used option so far."""
    count = dict.fromkeys(audiences, 0)
    chosen = {}
    for i in sorted(range(len(bridges)), key=lambda i: len(bridges[i].audiences or audiences)):
        pick = min(bridges[i].audiences or audiences, key=count.__getitem__)  # ties go to the bridge's first-listed persona
        count[pick] += 1
        chosen[i] = audiences[pick]
    return [chosen[i] for i in range(len(bridges))]
