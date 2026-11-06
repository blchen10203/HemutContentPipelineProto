import datetime

import httpx
import pytest

import fetch_sources
from fetch_sources import html_to_text


def test_html_to_text():
    html = (
        "<html><head><title>T</title><style>x{}</style></head><body><h1>Price</h1>"
        "<p><span>$</span><span>99</span> /mo &amp; up</p><script>var a=1</script></body></html>"
    )
    assert html_to_text(html) == "T\nPrice\n$99 /mo & up\n"


def test_refuses_to_overwrite_todays_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_sources, "OUT", tmp_path)
    snapshot = tmp_path / f"pricing_{datetime.date.today().isoformat()}.txt"
    snapshot.write_text("cited")
    with pytest.raises(SystemExit):
        fetch_sources.main()
    assert snapshot.read_text() == "cited"


def test_named_sources_only(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_sources, "OUT", tmp_path)
    with pytest.raises(SystemExit, match="Unknown source"):
        fetch_sources.main(["no-such-page"])
    snapshot = tmp_path / f"iftach-carriers_{datetime.date.today().isoformat()}.txt"
    snapshot.write_text("cited")
    with pytest.raises(SystemExit, match="iftach-carriers"):
        fetch_sources.main(["iftach-carriers"])
    assert snapshot.read_text() == "cited"


class FakeClient:
    def __init__(self, text, content_type): self.r = httpx.Response(200, text=text, headers={"content-type": content_type}, request=httpx.Request("GET", "https://hemut.com/x"))
    def get(self, url): return self.r


def test_snapshot_writes_text_and_html(tmp_path):
    day = datetime.date(2026, 11, 6)
    path = fetch_sources.snapshot("voice", "https://hemut.com/x", out=tmp_path, today=day,
                                  client=FakeClient("<p>Hi</p>", "text/html"))
    assert path == tmp_path / "voice_2026-11-06.txt" and path.read_text(encoding="utf-8") == "Hi\n"
    assert (tmp_path / "voice_2026-11-06.html").read_text() == "<p>Hi</p>"


def test_snapshot_refuses_existing_dated_file(tmp_path):
    (tmp_path / "voice_2026-11-06.txt").write_text("cited")
    with pytest.raises(FileExistsError):
        fetch_sources.snapshot("voice", "https://hemut.com/x", out=tmp_path, today=datetime.date(2026, 11, 6),
                               client=FakeClient("new", "text/plain"))
    assert (tmp_path / "voice_2026-11-06.txt").read_text() == "cited"
