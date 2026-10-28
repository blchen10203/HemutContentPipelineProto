"""scripts/run_eval.py --only filter. No network: nothing here runs a request."""
import pytest

from scripts.run_eval import select

REQUESTS = [{"text": "IFTA ad"}, {"text": "Fuel card deal"}, {"text": "Rate cons from email"}]


def test_no_filter_keeps_all():
    assert select(REQUESTS, []) == REQUESTS


def test_by_index_and_by_substring():
    assert select(REQUESTS, ["2"]) == [REQUESTS[1]]  # 1-based, as run_eval's progress lines count
    assert select(REQUESTS, ["rate CONS", "1"]) == [REQUESTS[0], REQUESTS[2]]  # file order, case-insensitive


def test_no_match_stops_before_spending():
    with pytest.raises(SystemExit, match="matches no request"):
        select(REQUESTS, ["99"])
