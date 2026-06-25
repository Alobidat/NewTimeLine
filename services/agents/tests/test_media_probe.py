"""Unit tests for the media-probe agent's ffprobe/ffmpeg parsing.

``subprocess.run`` is monkeypatched, so these run without an ffmpeg binary present.
"""

from __future__ import annotations

import json
import subprocess

from chronos_agents import media_probe


class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = b""


def test_ffprobe_parses_dimensions_and_duration(monkeypatch):
    meta = {
        "streams": [
            {"codec_type": "audio"},
            {"codec_type": "video", "width": 1920, "height": 1080},
        ],
        "format": {"duration": "12.84"},
    }
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, json.dumps(meta).encode()))
    assert media_probe._ffprobe("/x") == {"width": 1920, "height": 1080, "duration_s": 12}


def test_ffprobe_swaps_dimensions_for_portrait_rotation(monkeypatch):
    meta = {
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "tags": {"rotate": "-90"}}
        ],
        "format": {"duration": "5"},
    }
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, json.dumps(meta).encode()))
    out = media_probe._ffprobe("/x")
    assert out["width"] == 1080 and out["height"] == 1920


def test_ffprobe_none_without_video_stream(monkeypatch):
    meta = {"streams": [{"codec_type": "audio"}], "format": {"duration": "5"}}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, json.dumps(meta).encode()))
    assert media_probe._ffprobe("/x") is None


def test_ffprobe_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(1, b""))
    assert media_probe._ffprobe("/x") is None


def test_ffprobe_none_when_binary_missing(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(subprocess, "run", boom)
    assert media_probe._ffprobe("/x") is None


def test_ffposter_returns_bytes_falling_back_to_frame_zero(monkeypatch):
    calls = {"n": 0}

    def fake_run(cmd, *a, **k):
        calls["n"] += 1
        # First attempt (-ss 1) fails on a sub-1s clip; the -ss 0 retry succeeds.
        return _Proc(1, b"") if calls["n"] == 1 else _Proc(0, b"\xff\xd8jpeg")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert media_probe._ffposter("/x") == b"\xff\xd8jpeg"
    assert calls["n"] == 2


def test_ffposter_none_when_all_attempts_fail(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(1, b""))
    assert media_probe._ffposter("/x") is None
