"""Thin async client for the ComfyUI media-AI generator (the platform's render backend).

ComfyUI runs on a GPU box (RTX 3090) and exposes a prompt-graph HTTP API. This module builds the
workflow graph, submits it (`POST /prompt`), polls `/history/{id}`, and fetches the rendered bytes
(`/view`). Today it drives **LTX-Video** text-to-video (the validated workflow); image/other models
can be added as more `build_*` graphs. Bounded + best-effort: any failure returns ``None`` so the
calling agent degrades gracefully rather than crashing a worker.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("chronos.agents.comfyui")

# LTX-Video wants a frame count of the form 8n+1; 25 fps is its native rate.
LTXV_FPS = 25
LTXV_CKPT = "ltx-video-2b-v0.9.5.safetensors"
LTXV_T5 = "t5xxl_fp16.safetensors"
SDXL_CKPT = "sd_xl_base_1.0.safetensors"
_DEFAULT_NEG = "low quality, worst quality, blurry, distorted, static, watermark, text, deformed"
# SDXL stays sharp/coherent up to ~1:1.6; 832x1216 is the standard portrait the feed (9:16) crops.
_IMG_NEG = ("low quality, worst quality, blurry, deformed, disfigured, watermark, signature, "
            "text, caption, subtitles, logo, frame, border, ugly, jpeg artifacts")


def snap_length(seconds: float, *, fps: int = LTXV_FPS, max_frames: int = 161) -> int:
    """Frames for ``seconds`` of video, snapped to LTX's required 8n+1 and capped."""
    frames = max(int(round(seconds * fps)), 9)
    frames = min(frames, max_frames)
    # round down to the nearest 8n+1
    return ((frames - 1) // 8) * 8 + 1


def build_ltxv_text2video(
    prompt: str,
    *,
    negative: str = _DEFAULT_NEG,
    width: int = 768,
    height: int = 512,
    length: int = 97,
    steps: int = 20,
    cfg: float = 3.0,
    seed: int = 0,
    filename_prefix: str = "chronos/news",
) -> dict:
    """The LTX-Video text-to-video prompt graph (validated against ComfyUI 0.15 LTXV nodes)."""
    return {
        "ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": LTXV_CKPT}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": LTXV_T5, "type": "ltxv"}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["clip", 0]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["clip", 0]}},
        "lat": {"class_type": "EmptyLTXVLatentVideo",
                "inputs": {"width": width, "height": height, "length": length, "batch_size": 1}},
        "msl": {"class_type": "ModelSamplingLTXV",
                "inputs": {"model": ["ckpt", 0], "max_shift": 2.05, "base_shift": 0.95}},
        "cond": {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0],
                            "frame_rate": float(LTXV_FPS)}},
        "sched": {"class_type": "LTXVScheduler",
                  "inputs": {"steps": steps, "max_shift": 2.05, "base_shift": 0.95,
                             "stretch": True, "terminal": 0.1}},
        "samp": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "sc": {"class_type": "SamplerCustom",
               "inputs": {"model": ["msl", 0], "add_noise": True, "noise_seed": seed, "cfg": cfg,
                          "positive": ["cond", 0], "negative": ["cond", 1],
                          "sampler": ["samp", 0], "sigmas": ["sched", 0],
                          "latent_image": ["lat", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["sc", 0], "vae": ["ckpt", 2]}},
        "cv": {"class_type": "CreateVideo",
               "inputs": {"images": ["dec", 0], "fps": float(LTXV_FPS)}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["cv", 0], "filename_prefix": filename_prefix,
                            "format": "mp4", "codec": "h264"}},
    }


def _find_output_file(history_entry: dict) -> tuple[str, str] | None:
    """Pull the first rendered file (filename, subfolder) out of a /history outputs blob."""
    for out in history_entry.get("outputs", {}).values():
        for key in ("videos", "gifs", "images"):  # SaveVideo lands under one of these
            for f in out.get(key, []):
                name = f.get("filename", "")
                if name:
                    return name, f.get("subfolder", "")
    return None


async def run_workflow(
    base_url: str, graph: dict, *, timeout_s: int = 600, poll_s: float = 4.0
) -> bytes | None:
    """Submit a prompt graph, wait for it to finish, and return the rendered bytes (or None)."""
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(f"{base}/prompt", json={"prompt": graph})
            resp.raise_for_status()
            pid = resp.json().get("prompt_id")
            if not pid:
                log.warning("comfyui: no prompt_id in response")
                return None

            waited = 0.0
            while waited < timeout_s:
                await asyncio.sleep(poll_s)
                waited += poll_s
                h = (await client.get(f"{base}/history/{pid}")).json()
                entry = h.get(pid)
                if not entry:
                    continue
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    log.warning("comfyui: workflow %s errored", pid)
                    return None
                if not status.get("completed"):
                    continue
                found = _find_output_file(entry)
                if not found:
                    log.warning("comfyui: %s completed with no output file", pid)
                    return None
                filename, subfolder = found
                view = await client.get(
                    f"{base}/view",
                    params={"filename": filename, "subfolder": subfolder, "type": "output"},
                )
                view.raise_for_status()
                return view.content
            log.warning("comfyui: workflow %s timed out after %ss", pid, timeout_s)
            return None
    except Exception:  # noqa: BLE001 - render failures must not crash the worker
        log.warning("comfyui: run_workflow failed", exc_info=True)
        return None


async def generate_video(
    base_url: str,
    prompt: str,
    *,
    negative: str = _DEFAULT_NEG,
    seconds: float = 4.0,
    width: int = 768,
    height: int = 512,
    steps: int = 20,
    seed: int = 0,
    timeout_s: int = 600,
) -> tuple[bytes, int, int, int] | None:
    """Generate a clip from ``prompt`` via LTX-Video → ``(mp4_bytes, w, h, frames)`` or None."""
    length = snap_length(seconds)
    graph = build_ltxv_text2video(
        prompt, negative=negative, width=width, height=height, length=length, steps=steps, seed=seed
    )
    data = await run_workflow(base_url, graph, timeout_s=timeout_s)
    if not data:
        return None
    return data, width, height, length


def build_sdxl_text2image(
    prompt: str,
    *,
    negative: str = _IMG_NEG,
    width: int = 832,
    height: int = 1216,
    steps: int = 30,
    cfg: float = 7.0,
    seed: int = 0,
    filename_prefix: str = "chronos/scene",
) -> dict:
    """An SDXL text-to-image prompt graph (validated against ComfyUI 0.15)."""
    return {
        "ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": SDXL_CKPT}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["ckpt", 1]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["ckpt", 1]}},
        "lat": {"class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1}},
        "k": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "dpmpp_2m",
                         "scheduler": "karras", "denoise": 1.0, "model": ["ckpt", 0],
                         "positive": ["pos", 0], "negative": ["neg", 0],
                         "latent_image": ["lat", 0]}},
        "dec": {"class_type": "VAEDecode", "inputs": {"samples": ["k", 0], "vae": ["ckpt", 2]}},
        "save": {"class_type": "SaveImage",
                 "inputs": {"filename_prefix": filename_prefix, "images": ["dec", 0]}},
    }


async def generate_image(
    base_url: str,
    prompt: str,
    *,
    negative: str = _IMG_NEG,
    width: int = 832,
    height: int = 1216,
    steps: int = 30,
    seed: int = 0,
    timeout_s: int = 300,
) -> bytes | None:
    """Generate one still (PNG bytes) from ``prompt`` via SDXL, or ``None`` on failure."""
    graph = build_sdxl_text2image(
        prompt, negative=negative, width=width, height=height, steps=steps, seed=seed
    )
    return await run_workflow(base_url, graph, timeout_s=timeout_s)
