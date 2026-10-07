"""Offline tests: FakeServer replaces urllib's network calls."""
import io
import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import seedance2  # noqa: E402


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeServer:
    """Plays the API: one job that is pending once, then done."""

    def __init__(self, final_status="done"):
        self.seen = []
        self.polls = 0
        self.final_status = final_status

    def __call__(self, request, timeout=None):
        body = json.loads(request.data) if request.data and request.get_method() == "POST" else None
        self.seen.append((request.get_method(), request.full_url, body, dict(request.header_items())))
        url = request.full_url
        if url.endswith("/videos/generations"):
            return Reply(json.dumps({"request_id": "job-7"}).encode())
        if url.endswith("/videos/job-7/content"):
            return Reply(b"MP4BYTES")
        if url.endswith("/videos/job-7"):
            self.polls += 1
            state = {"request_id": "job-7", "status": "pending", "progress": 50}
            if self.polls > 1:
                state = {"request_id": "job-7", "status": self.final_status, "progress": 100,
                         "video": {"url": "https://argolink.io/v1/videos/job-7/content"},
                         "usage": {"output_seconds": 6, "reference_video_seconds": 0, "billed_seconds": 6},
                         "error": {"code": "generation_failed", "message": "upstream error", "retryable": True}}
            return Reply(json.dumps(state).encode())
        raise AssertionError(f"unexpected call {url}")


@pytest.fixture
def server(monkeypatch):
    fake = FakeServer()
    monkeypatch.setattr(seedance2.urllib.request, "urlopen", fake)
    monkeypatch.setattr(seedance2.time, "sleep", lambda s: None)
    monkeypatch.setenv("SEEDANCE_API_KEY", "test-key")
    return fake


@pytest.mark.parametrize("endpoint,model", [
    ("bytedance/seedance-2.0/text-to-video", "seedance-2.0"),
    ("bytedance/seedance-2.0/fast/text-to-video", "seedance-2.0-fast"),
    ("bytedance/seedance-2.0/mini/text-to-video", "seedance-2.0-mini"),
])
def test_fal_text_calls_pick_the_model_and_convert_types(endpoint, model):
    body, dropped = seedance2.from_fal(endpoint, {"prompt": "p", "duration": "10", "aspect_ratio": "21:9",
                                                  "resolution": "480p", "codec": "H265", "end_user_id": "u1"})
    assert body == {"model": model, "prompt": "p", "duration": 10, "aspect_ratio": "21:9", "resolution": "480p"}
    assert dropped == ["end_user_id", "codec"]


def test_fal_auto_values_fall_back_to_api_defaults():
    body, _ = seedance2.from_fal("bytedance/seedance-2.0/text-to-video", {"prompt": "p", "duration": "auto", "aspect_ratio": "auto"})
    assert body == {"model": "seedance-2.0", "prompt": "p"}  # renders 5 s at 16:9 here
    frames, _ = seedance2.from_fal("bytedance/seedance-2.0/image-to-video",
                                   {"prompt": "p", "image_url": "https://x.test/a.png", "end_image_url": "https://x.test/b.png"})
    assert frames["aspect_ratio"] == "adaptive"
    assert frames["start_image"] == {"url": "https://x.test/a.png"} and frames["end_image"] == {"url": "https://x.test/b.png"}


def test_fal_reference_lists_are_renamed():
    body, _ = seedance2.from_fal("bytedance/seedance-2.0/mini/reference-to-video",
                                 {"prompt": "@Image1 sings @Audio1", "image_urls": ["https://x.test/i.png"],
                                  "audio_urls": ["https://x.test/a.mp3"], "video_urls": []})
    assert body["reference_images"] == [{"url": "https://x.test/i.png"}]
    assert body["reference_audios"] == [{"url": "https://x.test/a.mp3"}]
    assert "reference_videos" not in body


def test_fal_calls_this_wrapper_cannot_translate_are_refused():
    with pytest.raises(seedance2.SeedanceError):
        seedance2.from_fal("bytedance/seedance-2.5/text-to-video", {"prompt": "p"})
    with pytest.raises(seedance2.SeedanceError, match="no equivalent for: num_frames"):
        seedance2.from_fal("bytedance/seedance-2.0/text-to-video", {"prompt": "p", "num_frames": 120})


def test_subscribe_runs_the_job_and_returns_a_fal_shaped_result(server, tmp_path):
    out = tmp_path / "clip.mp4"
    result = seedance2.subscribe("bytedance/seedance-2.0/fast/text-to-video", {"prompt": "a heron", "duration": "6"}, output=str(out))
    method, url, body, headers = server.seen[0]
    assert (method, url) == ("POST", "https://argolink.io/v1/videos/generations")
    assert body == {"model": "seedance-2.0-fast", "prompt": "a heron", "duration": 6}
    assert headers["Authorization"] == "Bearer test-key"
    assert result["video"]["url"].endswith("/videos/job-7/content")
    assert result["usage"]["billed_seconds"] == 6 and out.read_bytes() == b"MP4BYTES"


def test_every_request_names_the_client(server, tmp_path, monkeypatch):
    seedance2.subscribe("bytedance/seedance-2.0/text-to-video", {"prompt": "a heron"}, output=str(tmp_path / "a.mp4"))
    assert {headers.get("User-agent") for _, _, _, headers in server.seen} == {seedance2.USER_AGENT}

    picture = tmp_path / "frame.png"
    picture.write_bytes(b"PNG")
    sent = []

    def storage(request, timeout=None):
        sent.append((request.get_method(), dict(request.header_items())))
        if request.full_url.endswith("/media/uploads"):
            return Reply(json.dumps({"upload_url": "https://storage.test/put", "media_url": "https://media.test/m"}).encode())
        return Reply(b"")

    monkeypatch.setattr(seedance2.urllib.request, "urlopen", storage)
    assert seedance2.Seedance2(api_key="k").upload(str(picture)) == "https://media.test/m"
    assert [(method, headers["User-agent"]) for method, headers in sent] == [("POST", seedance2.USER_AGENT), ("PUT", seedance2.USER_AGENT)]
    assert "Authorization" not in sent[1][1]  # the storage PUT never carries the key


def test_failed_job_raises_with_the_job_attached(monkeypatch):
    fake = FakeServer(final_status="failed")
    monkeypatch.setattr(seedance2.urllib.request, "urlopen", fake)
    monkeypatch.setattr(seedance2.time, "sleep", lambda s: None)
    with pytest.raises(seedance2.SeedanceError, match="generation_failed") as raised:
        seedance2.Seedance2(api_key="k").wait("job-7")
    assert raised.value.payload["error"]["retryable"] is True


def test_http_errors_surface_the_api_message(monkeypatch):
    def reject(request, timeout=None):
        body = b'{"error": {"type": "invalid_request_error", "code": "request_unsupported", "message": "seedance-2.0-mini does not support video resolution 1080p"}}'
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(seedance2.urllib.request, "urlopen", reject)
    with pytest.raises(seedance2.SeedanceError, match="does not support video resolution 1080p") as raised:
        seedance2.Seedance2(api_key="k").submit("mini", "p", resolution="1080p")
    assert raised.value.status == 400


def test_cli_cost_needs_no_key(monkeypatch, capsys):
    monkeypatch.delenv("SEEDANCE_API_KEY", raising=False)
    assert seedance2.main(["cost", "--model", "mini", "--resolution", "480p", "--duration", "4"]) == 0
    assert json.loads(capsys.readouterr().out) == {"model": "seedance-2.0-mini", "resolution": "480p", "usd": 0.104}


def test_cli_t2v_no_wait_prints_the_request_id(server, capsys):
    assert seedance2.main(["t2v", "a heron", "--model", "fast", "--duration", "6", "--ratio", "9:16", "--silent", "--no-wait"]) == 0
    assert capsys.readouterr().out.strip() == "job-7"
    assert server.seen[0][2] == {"model": "seedance-2.0-fast", "prompt": "a heron", "duration": 6, "resolution": "720p",
                                 "aspect_ratio": "9:16", "generate_audio": False}


def test_cost_counts_whole_reference_seconds():
    assert seedance2.cost("seedance-2.0", "720p", 5, 2.4) == pytest.approx(0.77)
    with pytest.raises(seedance2.SeedanceError):
        seedance2.cost("fast", "4k", 5)
