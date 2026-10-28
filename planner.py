"""Weekly content plan for Mode B: active seasons first (the boost), then evergreen pillars.

One angle per tag per week. A tag with several bridge entries rotates through them by week number, so consecutive
weeks lead with different angles without any stored history. The evergreen pillars rotate the same way, so the
slots left after the seasons go to different pillars each week. Two tags never sell the same hemut_feature in one week.
Once the slots are filled, each gets a reader persona from its bridge's audiences, spread so a week repeats one as little as it can.
"""
import datetime

from brief_sources.seasonal import active_seasons, bridge_brief
from knowledge.loader import load_audiences, load_bridges, load_seasons
from schemas import AudienceProfile, BridgeEntry, PlanItem, SeasonWindow

SLOTS = 5


def plan_week(
    today: datetime.date,
    *,
    seasons: list[SeasonWindow] | None = None,
    bridges: list[BridgeEntry] | None = None,
    audiences: dict[str, AudienceProfile] | None = None,
    slots: int = SLOTS,
    skipped: list[str] | None = None,  # if given, gets one plain-English line per thing left out, for a human
) -> list[PlanItem]:
    seasons = load_seasons() if seasons is None else seasons
    bridges = load_bridges() if bridges is None else bridges
    audiences = load_audiences() if audiences is None else audiences
    skipped = [] if skipped is None else skipped

    candidates = [(b, "seasonal", reason) for b, reason in active_seasons(today, seasons, bridges)]
    candidates += [(b, "evergreen", f"Evergreen pillar: {b.tag.removeprefix('evergreen-')}")
                   for b in bridges if b.tag.startswith("evergreen-")]

    week = (today.toordinal() - 1) // 7  # weeks since a Monday, unbroken across years (ISO week 53 would repeat)
    by_tag: dict[str, list] = {}
    for c in candidates:
        by_tag.setdefault(c[0].tag, []).append(c)
    groups = [_rotate(group, week) for group in by_tag.values()]
    pillars = [g for g in groups if g[0][1] == "evergreen"]  # listed after the seasons
    candidates = [c for group in groups[:len(groups) - len(pillars)] + _rotate(pillars, week) for c in group]

    picked, tags, features = [], set(), set()
    for bridge, origin, reason in candidates:
        tag = bridge.tag
        if tag in tags:
            continue  # this tag's other angle is already in the plan, or the tag is already reported as out of slots
        elif bridge.hemut_feature in features:
            skipped.append(f"{tag}: same feature already in this week's plan ({bridge.hemut_feature})")
        elif len(picked) >= slots:
            skipped.append(f"{tag}: no slot left this week")
            tags.add(tag)  # one line per tag, not one per angle
        else:
            picked.append((bridge, origin, reason))
            tags.add(tag)
            features.add(bridge.hemut_feature)

    personas = _personas([b for b, _, _ in picked], audiences)
    return [PlanItem(brief=bridge_brief(b, origin, persona), reason=f"{reason} · Reader: {persona.label}")
            for (b, origin, reason), persona in zip(picked, personas)]


def _rotate(items: list, week: int) -> list:
    n = week % len(items) if items else 0
    return items[n:] + items[:n]


def _personas(bridges: list[BridgeEntry], audiences: dict[str, AudienceProfile]) -> list[AudienceProfile]:
    """One persona per slot: slots with the fewest options choose first, each taking its least-used option so far."""
    count = dict.fromkeys(audiences, 0)
    chosen = {}
    for i in sorted(range(len(bridges)), key=lambda i: len(bridges[i].audiences or audiences)):
        pick = min(bridges[i].audiences or audiences, key=count.__getitem__)  # ties go to the bridge's first-listed persona
        count[pick] += 1
        chosen[i] = audiences[pick]
    return [chosen[i] for i in range(len(bridges))]
