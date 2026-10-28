import base64

import pytest

import generate

TINY_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


@pytest.fixture(autouse=True)
def no_photos(monkeypatch, tmp_path_factory):
    # assets/ is local only, so tests never read it; photos() gives a test its own
    monkeypatch.setattr(generate, "PHOTOS", tmp_path_factory.mktemp("no-photos"))


@pytest.fixture
def photos(monkeypatch, tmp_path_factory):
    folder = tmp_path_factory.mktemp("photos")
    for name in ("demo-road.png", "launch-truck.jpg", "core-page_hero-bg.png"):  # the last is not in PHOTO_NAMES
        (folder / name).write_bytes(TINY_PNG)
    monkeypatch.setattr(generate, "PHOTOS", folder)
    return folder
