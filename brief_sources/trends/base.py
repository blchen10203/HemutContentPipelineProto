"""The one interface every trend source implements, so adding or swapping a platform touches one file."""
from typing import Protocol

from schemas import TrendCard, TrendItem


class TrendSource(Protocol):
    def fetch(self) -> tuple[list[TrendItem], list[TrendCard]]:
        """Items seen, grouped into cards. Sources report sensitivity and expiry; the planner decides what to use."""
        ...
