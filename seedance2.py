#!/usr/bin/env python3
"""seedance2.py: Seedance 2.0 video generation in one dependency-free file.

Library
    from seedance2 import Seedance2, subscribe

    Seedance2().run("seedance-2.0-mini", "A heron lands on a misty lake", "heron.mp4", duration=6)

    # a call written for fal's Seedance 2.0 endpoints, unchanged
    subscribe("bytedance/seedance-2.0/fast/text-to-video",
              arguments={"prompt": "A heron lands on a misty lake", "duration": "6"},
              output="heron.mp4")

Command line
    python seedance2.py t2v "A heron lands on a misty lake" --model mini --resolution 480p -o heron.mp4
    python seedance2.py --help

Python 3.8+, standard library only. Reads SEEDANCE_API_KEY; SEEDANCE_BASE_URL
defaults to https://argolink.io/v1. Community code, not affiliated with ByteDance or fal.
"""
from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

__version__ = "1.0.0"
DEFAULT_BASE_URL = "https://argolink.io/v1"
USER_AGENT = f"seedance-2-0-python-wrapper/{__version__}"  # sent on every request, uploads included

# USD per output second, read from the model pages on 2026-10-07.
PRICES: Dict[str, Dict[str, float]] = {
    "seedance-2.0": {"480p": 0.053, "720p": 0.11, "1080p": 0.28, "4k": 0.58},
    "seedance-2.0-fast": {"480p": 0.042, "720p": 0.091},
    "seedance-2.0-mini": {"480p": 0.026, "720p": 0.057},
}
ALIASES = {"2.0": "seedance-2.0", "standard": "seedance-2.0", "fast": "seedance-2.0-fast", "mini": "seedance-2.0-mini"}
UPLOAD_TYPES = {"image/jpeg": "image", "image/png": "image", "video/mp4": "video", "video/quicktime": "video",
                "audio/mpeg": "audio", "audio/wav": "audio", "audio/x-wav": "audio"}


class SeedanceError(RuntimeError):
    """An HTTP error from the API, a job that ended without a video, or a call this wrapper cannot translate."""

    def __init__(self, message: str, status: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def model_id(name: str) -> str:
    return ALIASES.get(name, name)


def cost(model: str, resolution: str = "720p", duration: int = 5, reference_video_seconds: float = 0.0) -> float:
    """USD for one job: per-second rate x (output seconds + whole seconds of reference video)."""
    rates = PRICES[model_id(model)]
    if resolution not in rates:
        raise SeedanceError(f"{model_id(model)} renders {', '.join(rates)}, not {resolution}")
    return round(rates[resolution] * (duration + math.floor(reference_video_seconds + 1e-9)), 4)


# --------------------------------------------------------------------------- fal compatibility
FAL_PREFIX = "bytedance/seedance-2.0/"
FAL_TIERS = {"": "seedance-2.0", "fast": "seedance-2.0-fast", "mini": "seedance-2.0-mini"}
FAL_TASKS = ("text-to-video", "image-to-video", "reference-to-video")
FAL_ONLY = ("end_user_id", "bitrate_mode", "codec", "seed")  # fal fields with no equivalent on this API


def from_fal(endpoint: str, arguments: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Translate a fal Seedance 2.0 call into a /v1/videos request body.

    Returns (body, dropped) where dropped lists the fal-only fields that were left out.
    """
    tier, _, task = endpoint[len(FAL_PREFIX):].rpartition("/") if endpoint.startswith(FAL_PREFIX) else ("?", "", "")
    if tier not in FAL_TIERS or task not in FAL_TASKS:
        raise SeedanceError(f"not a Seedance 2.0 endpoint on fal: {endpoint}")
    args = dict(arguments)
    dropped = [name for name in FAL_ONLY if args.pop(name, None) is not None]
    body: Dict[str, Any] = {"model": FAL_TIERS[tier], "prompt": args.pop("prompt", None)}

    duration = str(args.pop("duration", "auto"))
    if duration != "auto":  # fal sends "4".."15" as strings; this API takes an integer
        body["duration"] = int(duration)
    ratio = args.pop("aspect_ratio", "auto")
    if ratio != "auto":
        body["aspect_ratio"] = ratio
    elif task == "image-to-video":
        body["aspect_ratio"] = "adaptive"  # follow the first frame, as fal's "auto" does
    for name in ("resolution", "generate_audio"):
        if name in args:
            body[name] = args.pop(name)

    if task == "image-to-video":
        body["start_image"] = {"url": args.pop("image_url")}
        last = args.pop("end_image_url", None)
        if last:
            body["end_image"] = {"url": last}
    elif task == "reference-to-video":
        for fal_name, name in (("image_urls", "reference_images"), ("video_urls", "reference_videos"),
                               ("audio_urls", "reference_audios")):
            urls = args.pop(fal_name, None) or []
            if urls:
                body[name] = [{"url": url} for url in urls]
    if args:
        raise SeedanceError(f"no equivalent for: {', '.join(sorted(args))}")
    return body, dropped


# --------------------------------------------------------------------------- client
class Seedance2:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 poll_every: float = 10.0, timeout: float = 60.0):
        self.api_key = api_key or os.environ.get("SEEDANCE_API_KEY", "")
        if not self.api_key:
            raise SeedanceError("set SEEDANCE_API_KEY (or pass api_key)")
        self.base_url = (base_url or os.environ.get("SEEDANCE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.poll_every = poll_every
        self.timeout = timeout

    def _call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None, raw: bool = False) -> Any:
        request = urllib.request.Request(self.base_url + path, method=method,
                                         data=None if body is None else json.dumps(body).encode("utf-8"))
        request.add_header("Authorization", "Bearer " + self.api_key)
        request.add_header("User-Agent", USER_AGENT)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except urllib.error.HTTPError as error:
            text = error.read().decode("utf-8", "replace")
            try:
                payload: Any = json.loads(text)
            except ValueError:
                payload = text
            error_object = payload.get("error") if isinstance(payload, dict) else None
            message = error_object.get("message", text) if isinstance(error_object, dict) else text
            raise SeedanceError(f"{method} {path}: HTTP {error.code}: {str(message)[:300]}", error.code, payload) from None
        return data if raw else json.loads(data)

    def submit(self, model: str, prompt: str, **fields: Any) -> str:
        """Start a job; fields are request fields (duration, resolution, aspect_ratio, start_image, ...)."""
        body = {"model": model_id(model), "prompt": prompt, **fields}
        return self._call("POST", "/videos/generations", body)["request_id"]

    def status(self, request_id: str) -> Dict[str, Any]:
        return self._call("GET", f"/videos/{request_id}")

    def wait(self, request_id: str, max_wait: float = 1800,
             on_update: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        give_up = time.monotonic() + max_wait
        while True:
            job = self.status(request_id)
            if job.get("status") == "done":
                return job
            if job.get("status") in ("failed", "expired"):
                error = job.get("error") or {}
                raise SeedanceError(f"job {request_id} {job['status']}: {error.get('code', '')} {error.get('message', '')}".strip(),
                                    payload=job)
            if on_update:
                on_update(job)
            if time.monotonic() >= give_up:
                raise SeedanceError(f"job {request_id} still pending after {max_wait:.0f}s; check it later", payload=job)
            time.sleep(self.poll_every)

    def download(self, request_id: str, path: str) -> str:
        data = self._call("GET", f"/videos/{request_id}/content", raw=True)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def upload(self, path: str, model: str = "seedance-2.0") -> str:
        """Upload a local JPEG/PNG, MP4/MOV or MP3/WAV file; returns the media_url to send."""
        content_type = mimetypes.guess_type(path)[0] or ""
        kind = UPLOAD_TYPES.get(content_type)
        if not kind:
            raise SeedanceError(f"{path}: use JPEG/PNG images, MP4/MOV video or MP3/WAV audio")
        if content_type == "audio/x-wav":
            content_type = "audio/wav"
        ticket = self._call("POST", "/media/uploads", {"model": model_id(model), "type": kind,
                                                       "content_type": content_type, "size_bytes": os.path.getsize(path)})
        with open(path, "rb") as handle:
            put = urllib.request.Request(ticket["upload_url"], data=handle.read(), method="PUT")
        put.add_header("Content-Type", content_type)  # exactly the declared type, and no API key
        put.add_header("User-Agent", USER_AGENT)
        urllib.request.urlopen(put, timeout=600).close()
        return ticket["media_url"]

    def run(self, model: str, prompt: str, output: Optional[str] = None,
            on_update: Optional[Callable[[Dict[str, Any]], None]] = None, **fields: Any) -> Dict[str, Any]:
        """submit + wait (+ download when output is given). Returns the finished job."""
        request_id = self.submit(model, prompt, **fields)
        job = self.wait(request_id, on_update=on_update)
        if output:
            self.download(request_id, output)
        return job


def subscribe(endpoint: str, arguments: Dict[str, Any], *, output: Optional[str] = None,
              on_queue_update: Optional[Callable[[Dict[str, Any]], None]] = None,
              client: Optional[Seedance2] = None) -> Dict[str, Any]:
    """Run a fal-style Seedance 2.0 call and return a fal-shaped result.

    result["video"]["url"] needs your API key to download (fal's URL is public); pass
    output= to save the file. result["usage"]["billed_seconds"] is what the job cost.
    """
    body, dropped = from_fal(endpoint, arguments)
    if dropped:
        print(f"seedance2: left out fal-only fields: {', '.join(dropped)}", file=sys.stderr)
    client = client or Seedance2()
    model, prompt = body.pop("model"), body.pop("prompt")
    job = client.run(model, prompt, output=output, on_update=on_queue_update, **body)
    return {"video": {"url": (job.get("video") or {}).get("url")}, "request_id": job.get("request_id"),
            "usage": job.get("usage"), "saved_to": output}


# --------------------------------------------------------------------------- command line
def _media(client: Seedance2, value: str, model: str) -> Dict[str, str]:
    return {"url": value if value.startswith("https://") else client.upload(value, model)}


def _progress(job: Dict[str, Any]) -> None:
    left = job.get("estimated_seconds_remaining")
    print(f"  {job.get('status')} {job.get('progress', 0)}%" + (f", ~{left}s left" if left else ""), file=sys.stderr)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="seedance2.py", description="Seedance 2.0 from the command line.")
    commands = parser.add_subparsers(dest="command", required=True)

    def job_command(name: str, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("prompt")
        sub.add_argument("--model", default="seedance-2.0", help="seedance-2.0 | fast | mini (or a full model ID)")
        sub.add_argument("--duration", type=int, default=5, help="4-15 seconds")
        sub.add_argument("--resolution", default="720p", help="480p | 720p | 1080p | 4k (1080p and 4k: seedance-2.0 only)")
        sub.add_argument("--ratio", help="21:9 16:9 4:3 1:1 3:4 9:16, or adaptive with frames")
        sub.add_argument("--silent", action="store_true", help="generate_audio: false")
        sub.add_argument("-o", "--output", default="output.mp4")
        sub.add_argument("--no-wait", action="store_true", help="print the request_id and exit")
        return sub

    job_command("t2v", "text to video")
    i2v = job_command("i2v", "first frame, or first + last frame")
    i2v.add_argument("--first", required=True, help="https URL or local JPEG/PNG")
    i2v.add_argument("--last", help="https URL or local JPEG/PNG")
    ref = job_command("ref", "reference images, videos and audio (@Image 1, @Video 1, @Audio 1)")
    for flag in ("--image", "--video", "--audio"):
        ref.add_argument(flag, action="append", default=[], help="https URL or local file; repeat for more")

    commands.add_parser("status", help="print a job").add_argument("request_id")
    get = commands.add_parser("get", help="wait for a job and download it")
    get.add_argument("request_id")
    get.add_argument("-o", "--output", default="output.mp4")
    commands.add_parser("upload", help="upload a local file, print its media_url").add_argument("path")
    price = commands.add_parser("cost", help="estimate a job's price (no key needed)")
    price.add_argument("--model", default="seedance-2.0")
    price.add_argument("--resolution", default="720p")
    price.add_argument("--duration", type=int, default=5)
    price.add_argument("--ref-video-seconds", type=float, default=0.0)
    fal = commands.add_parser("fal", help="run a fal-style call: ENDPOINT 'JSON arguments'")
    fal.add_argument("endpoint")
    fal.add_argument("arguments")
    fal.add_argument("-o", "--output", default="output.mp4")

    args = parser.parse_args(argv)
    try:
        if args.command == "cost":
            print(json.dumps({"model": model_id(args.model), "resolution": args.resolution,
                              "usd": cost(args.model, args.resolution, args.duration, args.ref_video_seconds)}))
            return 0
        client = Seedance2()
        if args.command == "status":
            print(json.dumps(client.status(args.request_id), indent=2))
        elif args.command == "get":
            job = client.wait(args.request_id, on_update=_progress)
            client.download(args.request_id, args.output)
            print(json.dumps({"saved_to": args.output, "usage": job.get("usage")}))
        elif args.command == "upload":
            print(client.upload(args.path))
        elif args.command == "fal":
            print(json.dumps(subscribe(args.endpoint, json.loads(args.arguments), output=args.output,
                                       on_queue_update=_progress, client=client)))
        else:
            model = model_id(args.model)
            fields: Dict[str, Any] = {"duration": args.duration, "resolution": args.resolution}
            if args.ratio:
                fields["aspect_ratio"] = args.ratio
            if args.silent:
                fields["generate_audio"] = False
            if args.command == "i2v":
                fields["start_image"] = _media(client, args.first, model)
                fields.setdefault("aspect_ratio", "adaptive")
                if args.last:
                    fields["end_image"] = _media(client, args.last, model)
            elif args.command == "ref":
                for flag, name in (("image", "reference_images"), ("video", "reference_videos"), ("audio", "reference_audios")):
                    if getattr(args, flag):
                        fields[name] = [_media(client, value, model) for value in getattr(args, flag)]
            if args.no_wait:
                print(client.submit(model, args.prompt, **fields))
                return 0
            job = client.run(model, args.prompt, output=args.output, on_update=_progress, **fields)
            print(json.dumps({"saved_to": args.output, "request_id": job.get("request_id"), "usage": job.get("usage")}))
    except SeedanceError as error:
        print(f"error: {error}", file=sys.stderr)
        if isinstance(error.payload, dict):
            print(json.dumps(error.payload.get("error", error.payload), indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
