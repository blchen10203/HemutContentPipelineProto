import base64

import pytest

import generate
from schemas import Feature

TINY_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


@pytest.fixture(autouse=True)
def no_photos(monkeypatch, tmp_path_factory):
    # assets/ is local only, so tests never read it; photos() gives a test its own
    monkeypatch.setattr(generate, "PHOTOS", tmp_path_factory.mktemp("no-photos"))
    monkeypatch.setattr(generate, "SCREENSHOTS", tmp_path_factory.mktemp("no-screenshots"))


@pytest.fixture
def photos(monkeypatch, tmp_path_factory):
    folder = tmp_path_factory.mktemp("photos")
    for name in ("demo-road.png", "launch-truck.jpg", "core-page_hero-bg.png"):  # the last is not in PHOTO_NAMES
        (folder / name).write_bytes(TINY_PNG)
    monkeypatch.setattr(generate, "PHOTOS", folder)
    return folder


@pytest.fixture
def screenshots(monkeypatch, tmp_path_factory):
    folder = tmp_path_factory.mktemp("screenshots")
    for name in ("board-a.png", "board-b.png"):
        (folder / name).write_bytes(TINY_PNG)
    monkeypatch.setattr(generate, "SCREENSHOTS", folder)
    missing = {"file": "missing.png", "on_screen": "Missing"}
    features = {
        "dispatch-board-hos": Feature(id="dispatch-board-hos", label="Board", hemut_feature="Board", claim_ids=[], screenshots=[
            {"file": "board-a.png", "on_screen": "Board A"}, {"file": "board-b.png", "on_screen": "Board B"}, missing]),
        "ifta": Feature(id="ifta", label="IFTA", hemut_feature="IFTA", claim_ids=[], screenshots=[missing]),
    }
    monkeypatch.setattr(generate, "load_features", lambda: features)
    return folder
