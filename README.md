# Seedance 2.0 Python Wrapper — one file, from $0.026/s (Mini, 480p)

**ByteDance Seedance 2.0 is live on [ArgoLink](https://argolink.io/gh-seedance-2-0-python-wrapper)**: Mini from $0.026/s, Fast from $0.042/s and the full model from $0.053/s at 480p (up to $0.58/s at 4K), 25% below the official price. `seedance2.py` wraps it in a single dependency-free file you can drop into any project: a small Python API, a command-line tool, and a `subscribe()` that runs calls written for fal's Seedance 2.0 endpoints without edits.

[Model page →](https://argolink.io/en/models/seedance-2.0) · [Get the file](#get-the-file) · [CLI](#command-line) · [Python](#python) · [From fal](#moving-a-fal-call-over) · [FAQ](#faq)

<sub>Last checked: 2026-10-07. Python 3.8+, standard library only. Community code, not affiliated with ByteDance or fal.</sub>

## Get the file

```bash
curl -O https://raw.githubusercontent.com/marcellapemberton/seedance-2-0-python-wrapper/main/seedance2.py
export SEEDANCE_API_KEY=your-key        # from the ArgoLink console
python seedance2.py t2v "A heron lands on a misty lake at dawn" --model mini --resolution 480p -o heron.mp4
```

That 5-second draft costs 5 × $0.026 = $0.13. No `pip install`: the wrapper uses `urllib`, `json` and `argparse` only. `SEEDANCE_BASE_URL` (default `https://argolink.io/v1`) points it at any host that serves the same `/v1/videos` routes.

## Command line

| Command | What it does | Example |
|---|---|---|
| `t2v PROMPT` | text to video | `python seedance2.py t2v "rain on a tin roof, macro" --duration 8` |
| `i2v PROMPT --first IMG [--last IMG]` | first frame, or first + last frame; local files are uploaded | `python seedance2.py i2v "the door swings open" --first door.png` |
| `ref PROMPT --image … --video … --audio …` | reference mode; repeat a flag for more assets | `python seedance2.py ref "@Image 1 waves at the camera" --image me.png` |
| `status ID` | print a job as JSON | `python seedance2.py status 3f2c…` |
| `get ID [-o FILE]` | wait for a job, then download it | `python seedance2.py get 3f2c… -o clip.mp4` |
| `upload FILE` | upload a JPEG/PNG, MP4/MOV or MP3/WAV, print its `media_url` | `python seedance2.py upload frame.jpg` |
| `cost` | price a job; needs no key | `python seedance2.py cost --model 2.0 --resolution 4k --duration 6` |
| `fal ENDPOINT 'JSON'` | run a fal-style call | see [below](#moving-a-fal-call-over) |

Flags shared by `t2v`, `i2v` and `ref`:

| Flag | Default | Values |
|---|---|---|
| `--model` | `seedance-2.0` | `2.0`, `fast`, `mini` or a full model ID |
| `--duration` | 5 | 4–15 seconds |
| `--resolution` | `720p` | `480p`, `720p`; `1080p` and `4k` only on `seedance-2.0` |
| `--ratio` | 16:9 (`adaptive` for `i2v`) | `21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16`, `adaptive` with frames |
| `--silent` | off | sends `generate_audio: false` |
| `-o` | `output.mp4` | where to save the MP4 |
| `--no-wait` | off | print the `request_id` and exit; fetch later with `get` |

Progress goes to stderr, results to stdout as JSON, so the tool composes with `jq`:

```bash
ID=$(python seedance2.py t2v "a lighthouse in a storm, wide shot" --model fast --no-wait)
python seedance2.py get "$ID" -o lighthouse.mp4 | jq .usage.billed_seconds
```

## Python

```python
from seedance2 import Seedance2

client = Seedance2()                                      # SEEDANCE_API_KEY from the environment
job = client.run("seedance-2.0", "A glassblower turns a glowing vase, close-up, warm workshop light",
                 "vase.mp4", duration=10, resolution="1080p", aspect_ratio="4:3")
print(job["usage"])                                       # billed_seconds: 10 -> 10 x $0.28 = $2.80
```

| Function | Purpose |
|---|---|
| `Seedance2(api_key=None, base_url=None, poll_every=10, timeout=60)` | client; key and URL fall back to the environment |
| `.submit(model, prompt, **fields)` | `POST /v1/videos/generations`, returns `request_id` |
| `.status(request_id)` | `GET /v1/videos/{request_id}` |
| `.wait(request_id, max_wait=1800, on_update=None)` | polls until `done`; raises on `failed` / `expired` |
| `.download(request_id, path)` | `GET /v1/videos/{request_id}/content` into a file |
| `.upload(path, model="seedance-2.0")` | upload ticket + PUT, returns `media_url` (valid 7 days) |
| `.run(model, prompt, output=None, on_update=None, **fields)` | submit, wait, download |
| `subscribe(endpoint, arguments, *, output=None, on_queue_update=None)` | fal-style call, fal-shaped result |
| `from_fal(endpoint, arguments)` | the translation alone: returns `(body, dropped_fields)` |
| `cost(model, resolution, duration, reference_video_seconds=0)` | price in USD at the rates in `PRICES` |

`model` accepts the short names `2.0`, `fast` and `mini`. `**fields` are the API's own field names: `duration`, `resolution`, `aspect_ratio`, `generate_audio`, `start_image`, `end_image`, `reference_images`, `reference_videos`, `reference_audios`, each media item as `{"url": "https://…"}`.

## Moving a fal call over

fal exposes Seedance 2.0 as nine endpoints (standard, `fast/` and `mini/` × text-, image- and reference-to-video). `subscribe()` takes the same endpoint ID and `arguments`:

```python
from seedance2 import subscribe   # instead of: import fal_client; fal_client.subscribe(...)

result = subscribe(
    "bytedance/seedance-2.0/fast/image-to-video",
    arguments={"prompt": "She turns toward the window as the curtain moves", "image_url": "https://example.com/her.png",
               "duration": "6", "aspect_ratio": "auto", "resolution": "720p"},
    output="turn.mp4",
)
```

| fal argument | Sent as | Note |
|---|---|---|
| endpoint `…/seedance-2.0/…`, `…/fast/…`, `…/mini/…` | `model`: `seedance-2.0`, `seedance-2.0-fast`, `seedance-2.0-mini` | |
| `duration: "6"` | `duration: 6` | `"auto"` is left out, which renders 5 s here |
| `aspect_ratio: "auto"` | left out (16:9), or `adaptive` for image-to-video | |
| `image_url`, `end_image_url` | `start_image`, `end_image` | |
| `image_urls`, `video_urls`, `audio_urls` | `reference_images`, `reference_videos`, `reference_audios` | `@Image1` in the prompt still works |
| `resolution`, `generate_audio`, `prompt` | unchanged | |
| `codec`, `bitrate_mode`, `end_user_id`, `seed` | left out, with a note on stderr | no equivalent on this API |

Two behaviours differ from fal: the result's `video.url` must be downloaded with your API key (pass `output=` and the wrapper does it), and the result carries `usage.billed_seconds` instead of a seed.

## Price per output second

| Model | 480p | 720p | 1080p | 4K | fal, 720p ([fal pages](https://fal.ai/models/bytedance/seedance-2.0/text-to-video)) |
|---|---:|---:|---:|---:|---:|
| `seedance-2.0` | $0.053 | $0.11 | $0.28 | $0.58 | $0.3024 |
| `seedance-2.0-fast` | $0.042 | $0.091 | — | — | $0.2419 |
| `seedance-2.0-mini` | $0.026 | $0.057 | — | — | $0.1547 |

<sub>ArgoLink rates from the [Seedance 2.0](https://argolink.io/en/models/seedance-2.0), [Fast](https://argolink.io/en/models/seedance-2.0-fast) and [Mini](https://argolink.io/en/models/seedance-2.0-mini) pages; fal figures from its standard, fast and mini text-to-video pages. Both read 2026-10-07, no video input. fal bills tokens, (height × width × seconds × 24) / 1024, at $0.014, $0.0112 and $0.007 per 1,000 for the three tiers, and multiplies by 0.6 when a reference video is attached; here reference videos add their seconds at the normal rate.</sub>

## Recipes

```bash
# 4K first + last frame (seedance-2.0 only): 5 s x $0.58 = $2.90
python seedance2.py i2v "Clouds race over the valley as day turns to dusk" \
  --first https://example.com/day.png --last https://example.com/dusk.png --resolution 4k

# Character + voice: audio needs an image or video beside it on the 2.0 family
python seedance2.py ref "The man in @Image 1 says the line from @Audio 1, calm close-up" \
  --image portrait.png --audio line.mp3 --ratio 9:16

# Silent 9:16 clip for a captioned social post
python seedance2.py t2v "Hands knead bread dough on a floured table, top-down" --ratio 9:16 --silent
```

[examples/from_fal.py](./examples/from_fal.py) shows a reference-to-video call carried over from fal; [examples/prompt_list.py](./examples/prompt_list.py) renders a file of prompts as Mini drafts after confirming the total price.

## Limits worth knowing

| | |
|---|---|
| Duration | 4–15 whole seconds |
| References | 9 images, 3 videos, 3 audio clips, 15 total; videos and audio 2–15 s each, 15 s combined |
| Media | public `https://` URLs; local files go through `upload` first |
| Prompt | required in every mode |
| Unsupported | `seed`, `watermark: true`, more than one video per request |
| Job states | `pending` → `done`, or `failed` / `expired` (neither is billed) |

The wrapper does not re-check these limits; the API answers 400 with a message that the CLI prints, for example `seedance-2.0-mini does not support video resolution 1080p`.

## FAQ

**Why one file instead of a package?**
So it can be vendored: copy `seedance2.py` next to your code, or run it as a script on a server without a virtualenv. For a full package with typed errors and an MCP server, a heavier client is the better fit.

**Does `subscribe()` talk to fal?**
No. It reads fal's endpoint ID and argument names and sends an equivalent request to `SEEDANCE_BASE_URL`.

**What happens to fal's `"auto"` duration?**
The field is left out and the job renders and bills 5 seconds. Pass a number if your prompt needs more time.

**How do I resume after closing the terminal?**
Jobs keep running on the server. Run `python seedance2.py get REQUEST_ID` with the ID that `--no-wait` or the progress log printed.

**What is the cheapest test?**
`python seedance2.py t2v "…" --model mini --resolution 480p --duration 4`: $0.104.

## Tests

```bash
pip install pytest && pytest
```

The tests replace `urllib`'s network calls with a fake server: no key, no traffic.

## License

MIT
