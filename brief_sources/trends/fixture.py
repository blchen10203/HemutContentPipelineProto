"""Trend source that reads one frozen, dated YAML file. The demo's only trend source; no network."""
from pathlib import Path

from knowledge.loader import ROOT, _read_yaml
from schemas import TrendCard, TrendItem

# shortcut: Mode B reads this frozen fixture, swap in live sources (rss.py, federal_register.py, ...) after the demo
DEMO_FIXTURE = ROOT / "tests" / "fixtures" / "trends_2026-10-24.yaml"


class FixtureSource:
    def __init__(self, path: Path = DEMO_FIXTURE):
        self.path = path

    def fetch(self) -> tuple[list[TrendItem], list[TrendCard]]:
        raw = _read_yaml(self.path)
        items = [TrendItem.model_validate(i) for i in raw["items"]]
        cards = [TrendCard.model_validate(c) for c in raw["cards"]]
        unknown = {i for c in cards for i in c.items} - {i.id for i in items}
        if unknown:
            raise ValueError(f"{self.path}: cards reference unknown items {sorted(unknown)}")
        return items, cards
