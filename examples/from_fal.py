"""Move a fal Seedance 2.0 call over by changing the import.

Before (fal):
    import fal_client
    result = fal_client.subscribe("bytedance/seedance-2.0/reference-to-video", arguments={...})

After: the same endpoint ID and arguments. fal-only fields (codec, bitrate_mode,
end_user_id, seed) are left out with a note on stderr; "auto" duration renders 5 s.
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__) + "/..")
from seedance2 import subscribe  # noqa: E402

result = subscribe(
    "bytedance/seedance-2.0/reference-to-video",
    arguments={
        "prompt": "@Image1 walks through the rainy street from @Image2 at night, tracking shot, neon reflections",
        "image_urls": ["https://example.com/character.png", "https://example.com/street.jpg"],
        "resolution": "720p",
        "duration": "8",
        "aspect_ratio": "16:9",
        "generate_audio": True,
    },
    output="street.mp4",  # unlike fal, video.url needs your key, so let the wrapper download it
)
print(result["usage"])  # 8 billed seconds x $0.11 = $0.88 at the 2026-10-07 rate
