"""Tests for media extraction from feed entries (pure)."""

from __future__ import annotations

from chronos_agents.normalize import extract_media


def test_extracts_media_content_with_type_and_medium():
    out = extract_media({"media_content": [{"url": "http://x/a.bin", "medium": "image"}]})
    assert len(out) == 1 and out[0].kind == "image" and out[0].url == "http://x/a.bin"


def test_classifies_by_extension_when_no_mime():
    out = extract_media({"enclosures": [{"href": "http://x/clip.mp4"}]})
    assert out[0].kind == "video" and out[0].mime == "video/mp4"


def test_thumbnail_treated_as_image():
    out = extract_media({"media_thumbnail": [{"url": "http://x/t.jpg"}]})
    assert out[0].kind == "image"


def test_link_enclosures_are_picked_up():
    entry = {"links": [
        {"rel": "enclosure", "type": "image/png", "href": "http://x/p.png"},
        {"rel": "alternate", "href": "http://x/article"},  # ignored
    ]}
    out = extract_media(entry)
    assert len(out) == 1 and out[0].url == "http://x/p.png"


def test_dedups_and_skips_non_media():
    entry = {
        "media_content": [
            {"url": "http://x/a.jpg", "type": "image/jpeg"},
            {"url": "http://x/a.jpg", "type": "image/jpeg"},   # dup
            {"url": "http://x/page.html", "type": "text/html"},  # not media
        ]
    }
    out = extract_media(entry)
    assert len(out) == 1 and out[0].url == "http://x/a.jpg"


def test_respects_limit():
    entry = {"media_content": [{"url": f"http://x/{i}.jpg"} for i in range(20)]}
    assert len(extract_media(entry, limit=5)) == 5
