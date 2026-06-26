"""Compose an informative news clip from generated scene images + captions + narration.

Turns the anchor's script into a vertical (1080x1920) explainer: each scene's still gets a slow
Ken-Burns push, a persistent **headline** banner at the top, and the scene's **fact caption** at
the bottom; the scenes are concatenated to the length of the Piper **narration** WAV, which is
muxed as the audio track. Pure ffmpeg (the worker already has it) + DejaVu (already in the image).

`_scene_clip_args` is a pure arg-builder so the filter graph is unit-tested without ffmpeg; `render`
does the temp-file orchestration + subprocess and returns mp4 bytes (or ``None`` best-effort).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import textwrap

log = logging.getLogger("chronos.agents.news_video_render")

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FPS = 30
WIDTH, HEIGHT = 1080, 1920
_SCENE_TIMEOUT = 120
_MUX_TIMEOUT = 180


def _wrap(text: str, width: int) -> str:
    """Hard-wrap caption/headline text to lines for drawtext (which has no auto-wrap)."""
    text = " ".join((text or "").split())
    return "\n".join(textwrap.wrap(text, width)) or " "


def _probe_duration(ffmpeg: str, path: str) -> float | None:
    """Duration (seconds) of a media file via ffprobe (sits next to the ffmpeg binary)."""
    probe = (ffmpeg[:-6] + "ffprobe") if ffmpeg.endswith("ffmpeg") else "ffprobe"
    try:
        out = subprocess.run(
            [probe, "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, timeout=30,
        )
        return float(json.loads(out.stdout)["format"]["duration"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None


def _scene_clip_args(
    *, ffmpeg: str, image: str, headline_file: str, caption_file: str, out: str,
    frames: int, fps: int = FPS, width: int = WIDTH, height: int = HEIGHT, zoom_in: bool = True,
) -> list[str]:
    """ffmpeg command for ONE scene: cover-scale the still → Ken-Burns zoom → headline + caption
    banners → fixed-length silent clip. Pure (no I/O) so it's unit-tested."""
    # Pre-scale to 1.5x the frame so zoompan has clean pixels to sample (avoids jitter).
    sw, sh = int(width * 1.5), int(height * 1.5)
    z = "min(zoom+0.0009,1.25)" if zoom_in else "if(eq(on,0),1.25,max(zoom-0.0009,1.0))"
    vf = (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
        f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={width}x{height}:fps={fps},"
        # Persistent headline banner (top) + per-scene fact caption (bottom).
        f"drawtext=fontfile={FONT}:textfile={headline_file}:fontsize=52:fontcolor=white:"
        f"box=1:boxcolor=black@0.55:boxborderw=20:line_spacing=10:x=(w-text_w)/2:y=110,"
        f"drawtext=fontfile={FONT}:textfile={caption_file}:fontsize=44:fontcolor=white:"
        f"box=1:boxcolor=black@0.6:boxborderw=18:line_spacing=8:x=(w-text_w)/2:y=h-text_h-230,"
        f"format=yuv420p"
    )
    return [
        ffmpeg, "-nostdin", "-v", "error", "-y", "-i", image,
        "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out,
    ]


def render(
    scenes: list[tuple[bytes, str]],
    headline: str,
    narration_wav: bytes | None,
    *,
    ffmpeg: str = "ffmpeg",
    fallback_scene_seconds: float = 4.5,
    fps: int = FPS,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> tuple[bytes, int] | None:
    """Render ``scenes`` (image bytes + caption) into a captioned, narrated mp4.

    Returns ``(mp4_bytes, duration_seconds)`` or ``None``."""
    scenes = [s for s in scenes if s and s[0]]
    if not scenes:
        return None
    work = tempfile.mkdtemp(prefix="newsvid_")
    try:
        # The narration length sets the total runtime; split it evenly across scenes.
        narr_path = None
        if narration_wav:
            narr_path = os.path.join(work, "narration.wav")
            with open(narr_path, "wb") as f:
                f.write(narration_wav)
        total = (_probe_duration(ffmpeg, narr_path) if narr_path else None) \
            or (fallback_scene_seconds * len(scenes))
        per_scene = max(total / len(scenes), 1.5)
        frames = max(int(round(per_scene * fps)), 30)

        headline_file = os.path.join(work, "headline.txt")
        with open(headline_file, "w") as f:
            f.write(_wrap(headline, 34))

        scene_files = []
        for i, (img_bytes, caption) in enumerate(scenes):
            img = os.path.join(work, f"scene_{i}.png")
            with open(img, "wb") as f:
                f.write(img_bytes)
            cap = os.path.join(work, f"cap_{i}.txt")
            with open(cap, "w") as f:
                f.write(_wrap(caption, 38))
            out = os.path.join(work, f"clip_{i}.mp4")
            args = _scene_clip_args(
                ffmpeg=ffmpeg, image=img, headline_file=headline_file, caption_file=cap,
                out=out, frames=frames, fps=fps, width=width, height=height, zoom_in=(i % 2 == 0),
            )
            proc = subprocess.run(args, capture_output=True, timeout=_SCENE_TIMEOUT)
            if proc.returncode != 0 or not os.path.exists(out):
                log.warning("render: scene %d failed: %s",
                            i, proc.stderr[-300:].decode("utf8", "ignore"))
                return None
            scene_files.append(out)

        # Concat the scene clips (identical encode params → stream copy).
        concat_list = os.path.join(work, "list.txt")
        with open(concat_list, "w") as f:
            f.writelines(f"file '{p}'\n" for p in scene_files)
        out_path = os.path.join(work, "out.mp4")
        mux = [ffmpeg, "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", "0",
               "-i", concat_list]
        if narr_path:
            mux += ["-i", narr_path, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k",
                    "-shortest"]
        mux += ["-c:v", "copy", "-movflags", "+faststart", out_path]
        proc = subprocess.run(mux, capture_output=True, timeout=_MUX_TIMEOUT)
        if proc.returncode != 0 or not os.path.exists(out_path):
            log.warning("render: mux failed: %s", proc.stderr[-300:].decode("utf8", "ignore"))
            return None
        with open(out_path, "rb") as f:
            return f.read(), max(round(total), 1)
    except (OSError, subprocess.SubprocessError):
        log.warning("render: failed", exc_info=True)
        return None
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
