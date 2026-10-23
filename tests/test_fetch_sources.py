import datetime

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
