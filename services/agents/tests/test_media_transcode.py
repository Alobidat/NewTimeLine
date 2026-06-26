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
    monkeypatch.setattr(
        mt, "_transcode_mp4", lambda p, *, edit=None: (_ for _ in ()).throw(AssertionError())
    )
    out = mt._evaluate(b"fakebytes", "video/mp4", 1280)
    assert out == {"mode": "passthrough", "width": 1280, "height": 720}


def test_evaluate_transcodes_non_websafe_source(monkeypatch):
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: ("vp9", 1920, 1080))
    monkeypatch.setattr(mt, "_transcode_mp4", lambda p, *, edit=None: (b"\x00mp4", 1280, 720))
    out = mt._evaluate(b"fakebytes", "video/webm", 1920)
    assert out == {"mode": "transcoded", "data": b"\x00mp4", "width": 1280, "height": 720}


def test_evaluate_none_when_no_video_stream(monkeypatch):
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: (None, None, None))
    assert mt._evaluate(b"fakebytes", "video/mp4", None) is None


def test_evaluate_none_when_transcode_fails(monkeypatch):
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: ("vp9", 1920, 1080))
    monkeypatch.setattr(mt, "_transcode_mp4", lambda p, *, edit=None: None)
    assert mt._evaluate(b"fakebytes", "video/webm", 1920) is None


# --- Creator-Studio edit application (trim/speed) -------------------------------------


def test_build_args_no_edit_matches_baseline():
    args = mt._build_ffmpeg_args("/in", "/out.mp4")
    assert args[:5] == ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    assert "-ss" not in args and "-t" not in args and "-af" not in args
    # one -i, single scale filter, faststart output
    assert args.count("-i") == 1 and args[args.index("-i") + 1] == "/in"
    vf = args[args.index("-vf") + 1]
    assert vf == f"scale=min({mt.MAX_WIDTH}\\,iw):-2" and "setpts" not in vf
    assert args[-2:] == ["+faststart", "/out.mp4"]


def test_build_args_trim_uses_input_seek_and_duration():
    args = mt._build_ffmpeg_args("/in", "/out.mp4", {"trim_start": 1.5, "trim_end": 9.0})
    # -ss is an *input* option (before -i); duration -t = end - start = 7.5
    assert args.index("-ss") < args.index("-i")
    assert args[args.index("-ss") + 1] == "1.500"
    assert args[args.index("-t") + 1] == "7.500"


def test_build_args_trim_end_only_is_full_duration():
    args = mt._build_ffmpeg_args("/in", "/out.mp4", {"trim_end": 4.0})
    assert "-ss" not in args
    assert args[args.index("-t") + 1] == "4.000"


def test_build_args_speed_retimes_video_and_audio():
    args = mt._build_ffmpeg_args("/in", "/out.mp4", {"speed": 2.0})
    vf = args[args.index("-vf") + 1]
    assert "setpts=0.500000*PTS" in vf  # 1/2 speed-up of presentation timestamps
    assert args[args.index("-af") + 1] == "atempo=2.000"


def test_edit_forces_transcode_even_when_websafe(monkeypatch):
    # a clip that would normally passthrough must re-encode once it carries an edit
    monkeypatch.setattr(mt, "_probe_codec_dims", lambda p: ("h264", 1280, 720))
    seen = {}

    def fake_transcode(path, *, edit=None):
        seen["edit"] = edit
        return (b"\x00mp4", 1280, 720)

    monkeypatch.setattr(mt, "_transcode_mp4", fake_transcode)
    out = mt._evaluate(b"fakebytes", "video/mp4", 1280, {"speed": 2.0})
    assert out["mode"] == "transcoded"
    assert seen["edit"] == {"speed": 2.0}
