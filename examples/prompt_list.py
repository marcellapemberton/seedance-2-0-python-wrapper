"""Render every line of a text file as a draft on Seedance 2.0 Mini, after showing the total price.

    python examples/prompt_list.py prompts.txt
"""
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__) + "/..")
from seedance2 import Seedance2, SeedanceError, cost  # noqa: E402

MODEL, RESOLUTION, SECONDS = "seedance-2.0-mini", "480p", 5
prompts = [line.strip() for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
total = cost(MODEL, RESOLUTION, SECONDS) * len(prompts)
if input(f"{len(prompts)} clips x {SECONDS} s at {RESOLUTION} on {MODEL} = ${total:.2f}. Go? [y/N] ").lower() != "y":
    sys.exit(0)

client = Seedance2()
for number, prompt in enumerate(prompts, 1):
    try:
        job = client.run(MODEL, prompt, f"draft-{number:02d}.mp4", duration=SECONDS, resolution=RESOLUTION)
        print(f"draft-{number:02d}.mp4", job["usage"]["billed_seconds"], "s")
    except SeedanceError as error:  # a failed job is not billed; keep going
        print(f"draft-{number:02d} failed: {error}")
