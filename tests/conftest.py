import base64

import pytest

import generate
from schemas import Feature

TINY_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


@pytest.fixture(autouse=True)
def shots_dir(monkeypatch, tmp_path_factory):
    # assets/ is local only, so tests never read it; pool() and screenshots() put files in this empty folder
    folder = tmp_path_factory.mktemp("screenshots")
    monkeypatch.setattr(generate, "SCREENSHOTS", folder)
    return folder


@pytest.fixture
def pool(shots_dir):
    for name in ("help-center.jpg", "accounting-ifta.jpg", "crm-customers.jpg"):  # the last is not in RANDOM_SCREENSHOTS
        (shots_dir / name).write_bytes(TINY_PNG)
    return shots_dir


@pytest.fixture
def screenshots(shots_dir, monkeypatch):
    for name in ("board-a.png", "board-b.png"):
        (shots_dir / name).write_bytes(TINY_PNG)
    missing = {"file": "missing.png", "on_screen": "Missing"}
    features = {
        "dispatch-board-hos": Feature(id="dispatch-board-hos", label="Board", hemut_feature="Board", claim_ids=[], screenshots=[
            {"file": "board-a.png", "on_screen": "Board A"}, {"file": "board-b.png", "on_screen": "Board B"}, missing]),
        "ifta": Feature(id="ifta", label="IFTA", hemut_feature="IFTA", claim_ids=[], screenshots=[missing]),
    }
    monkeypatch.setattr(generate, "load_features", lambda: features)
    return shots_dir
