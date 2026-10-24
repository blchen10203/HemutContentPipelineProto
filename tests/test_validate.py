"""Golden set: every good post passes validate.py, every bad one gets at least its expected codes."""
from pathlib import Path
from typing import get_args

import pytest
import yaml

from knowledge.loader import load_claims, load_voice
from schemas import Violation
from validate import parse_post, validate

GOLDEN = Path(__file__).parent / "golden"
GOOD = sorted((GOLDEN / "good").glob("*.yaml"))
BAD = sorted((GOLDEN / "bad").glob("*.yaml"))
CLAIMS = load_claims()
VOICE = load_voice()


def check(path: Path) -> tuple[list[Violation], dict]:
    case = yaml.safe_load(path.read_text(encoding="utf-8"))
    post, violations = parse_post(case["post"])
    return (violations if post is None else validate(post, CLAIMS, VOICE)), case


@pytest.mark.parametrize("path", GOOD, ids=lambda p: p.stem)
def test_good_post_passes(path):
    violations, _ = check(path)
    assert violations == []


@pytest.mark.parametrize("path", BAD, ids=lambda p: p.stem)
def test_bad_post_is_caught(path):
    violations, case = check(path)
    assert set(case["expected_codes"]) <= {v.code for v in violations}, violations


def test_golden_set_covers_every_code():
    expected = {code for p in BAD for code in yaml.safe_load(p.read_text(encoding="utf-8"))["expected_codes"]}
    assert len(GOOD) >= 6 and len(BAD) >= 12
    assert expected == set(get_args(Violation.model_fields["code"].annotation))
