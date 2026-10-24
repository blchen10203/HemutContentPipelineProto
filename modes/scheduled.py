"""Mode B: plan the week, then run each PlanItem's Brief through the core pipeline."""
import datetime
from collections.abc import Iterator

from generate import run_brief
from planner import plan_week
from schemas import PlanItem, RunResult


def run_week(today: datetime.date, plan: list[PlanItem] | None = None, **run_kwargs) -> Iterator[RunResult]:
    """Yields each result as it finishes, so a failure later in the week does not hide earlier drafts.
    run_kwargs go to run_brief (client, on_event, out_root). One failed Brief stops the week; its run folder is kept."""
    for item in plan_week(today) if plan is None else plan:
        yield run_brief(item.brief, **run_kwargs)
