"""Unit tests for the media-transcode agent's decision + probe logic (ffmpeg mocked out)."""

from __future__ import annotations

import json
import subprocess

from chronos_agents import media_transcode as mt


class _Proc:
    def __init__(self, returncode: int = 0, stdout: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = b""


def test_needs_transcode_truth_table():
    # already web-safe: h264 in an mp4 container, within the width cap → no re-encode
    assert mt._needs_transcode("video/mp4", "h264", 1080) is False
    assert mt._needs_transcode("video/mp4", "h264", mt.MAX_WIDTH) is False
    # non-h264 codec, wrong container, or oversized → must transcode
    assert mt._needs_transcode("video/webm", "vp9", 720) is True
    assert mt._needs_transcode("video/quicktime", "h264", 720) is True
    assert mt._needs_transcode("video/mp4", "h264", mt.MAX_WIDTH + 1) is True
    assert mt._needs_transcode("video/mp4", None, 720) is True


def test_probe_codec_dims_parses_first_video_stream(monkeypatch):
    meta = {"streams": [
        {"codec_type": "audio", "codec_name": "aac"},
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
    ]}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, json.dumps(meta).encode()))
    assert mt._probe_codec_dims("/x") == ("h264", 1920, 1080)


def test_probe_codec_dims_none_when_unreadable(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(1, b""))
    assert mt._probe_codec_dims("/x") == (None, None, None)


def test_evaluate_passthrough_for_websafe_source(monkeypatch):
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: ("h264", 1280, 720))
    # _transcode_mp4 must NOT be called on a passthrough.
    monkeypatch.setattr(mt, "_transcode_mp4", lambda p: (_ for _ in ()).throw(AssertionError()))
    out = mt._evaluate(b"fakebytes", "video/mp4", 1280)
    assert out == {"mode": "passthrough", "width": 1280, "height": 720}


def test_evaluate_transcodes_non_websafe_source(monkeypatch):
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: ("vp9", 1920, 1080))
    monkeypatch.setattr(mt, "_transcode_mp4", lambda p: (b"\x00mp4", 1280, 720))
    out = mt._evaluate(b"fakebytes", "video/webm", 1920)
    assert out == {"mode": "transcoded", "data": b"\x00mp4", "width": 1280, "height": 720}


def test_evaluate_none_when_no_video_stream(monkeypatch):
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: (None, None, None))
    assert mt._evaluate(b"fakebytes", "video/mp4", None) is None


def test_evaluate_none_when_transcode_fails(monkeypatch):
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: ("vp9", 1920, 1080))
    monkeypatch.setattr(mt, "_transcode_mp4", lambda p: None)
    assert mt._evaluate(b"fakebytes", "video/webm", 1920) is None
