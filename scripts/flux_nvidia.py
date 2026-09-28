"""
flux_nvidia.py — text-free GoalFi background art from FLUX.1-dev on the NVIDIA API.
(Run every command from the GoalFi LinkedIn Studio root folder.)

FLUX can't take a reference image or edit one, and it can't be trusted with exact digits.
So it paints ONLY the background; brand_chart.py draws every headline, number and the logo
on top (--background), which makes the numbers correct by construction.

  python3.12 scripts/flux_nvidia.py --prompt-file posts/<slug>/bg_prompt.md --out posts/<slug>/bg.png
  python3.12 scripts/flux_nvidia.py --prompt "gold light trails rising over a navy grid" --n 3 --out posts/<slug>/bg.png
  python3.12 scripts/flux_nvidia.py --prompt "..." --seed 123456 --out ...     # reproduce an exact image

  then: python3.12 scripts/brand_chart.py --data posts/<slug>/chart.json --background posts/<slug>/bg.png --out posts/<slug>/image.png

API (docs.api.nvidia.com/nim/reference/black-forest-labs-flux_1-dev-infer):
  POST https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev, Bearer NVIDIA_API_KEY
  width/height in {768..1344 step 64}, cfg_scale (1,9], steps 5-100, seed 0=random, samples=1
  -> {"artifacts":[{"base64": <jpeg>, "finishReason": SUCCESS|CONTENT_FILTERED|ERROR, "seed": n}]}

LICENCE: NVIDIA lists FLUX.1-dev as "ready for non-commercial use" under the NVIDIA API Trial
Terms; commercial terms via sales@blackforestlabs.ai. Confirm before using on the company page.
Key: NVIDIA_API_KEY in the environment or in <studio root>/.env.
"""
import argparse
import base64
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

import _env

INVOKE_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"

# API size -> LinkedIn size. 1024x1280 is exactly 4:5.
ASPECTS = {
    "4:5": ((1024, 1280), (1080, 1350)),
    "1:1": ((1024, 1024), (1080, 1080)),
    "16:9": ((1344, 768), (1344, 768)),
}

# Brand direction for backgrounds. FLUX reads colour words better than hex codes.
BG_PREAMBLE = (
    "Premium abstract background for a financial research infographic. "
    "Deep midnight navy blue (#172554) dominant, with restrained metallic gold (#d29900) accents. "
    "Minimal, elegant, flat vector or soft 3D, subtle fine grid lines and soft depth, "
    "institutional investment-bank aesthetic. The top quarter and the centre must stay calm and "
    "uncluttered so headline text and a chart can be placed over them. "
    "Absolutely no text, no letters, no numbers, no logos, no watermarks, no people, no faces, "
    "no currency notes, no coins. Scene: "
)


def generate(prompt, aspect="4:5", steps=50, cfg_scale=3.5, seed=0, retries=3):
    key = _env.get("NVIDIA_API_KEY")
    if not key:
        sys.exit("No NVIDIA_API_KEY. Add it to .env (see .env.example).")
    (w, h), _ = ASPECTS[aspect]
    payload = {"prompt": prompt[:10000], "mode": "base", "cfg_scale": cfg_scale,
               "width": w, "height": h, "seed": seed, "steps": steps}
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=180)
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}: {r.text[:200]}"
            elif r.status_code == 422:
                sys.exit(f"Invalid request (422): {r.text[:500]}")
            else:
                r.raise_for_status()
                art = r.json()["artifacts"][0]
                if art.get("finishReason") != "SUCCESS":
                    sys.exit(f"Not generated: finishReason={art.get('finishReason')} — reword the prompt.")
                img = Image.open(BytesIO(base64.b64decode(art["base64"]))).convert("RGB")
                return img, art.get("seed", seed)
        except requests.RequestException as e:
            last = e
        time.sleep(5 * (attempt + 1))
    sys.exit(f"FLUX request failed after {retries} tries: {last}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--aspect", default="4:5", choices=list(ASPECTS))
    ap.add_argument("--n", type=int, default=1, help="variants (one API call each)")
    ap.add_argument("--seed", type=int, default=0, help="0 = random; reuse a saved seed to reproduce")
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--cfg", type=float, default=3.5, help="prompt adherence, >1 to 9")
    ap.add_argument("--raw", action="store_true", help="skip the brand background preamble")
    a = ap.parse_args()

    body = Path(a.prompt_file).read_text() if a.prompt_file else (a.prompt or "")
    if not body.strip():
        sys.exit("give --prompt or --prompt-file")
    prompt = body if a.raw else BG_PREAMBLE + body.strip()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _, final = ASPECTS[a.aspect]
    for k in range(a.n):
        path = out if a.n == 1 else out.with_name(f"{out.stem}_v{k + 1}{out.suffix}")
        img, seed = generate(prompt, a.aspect, a.steps, a.cfg, a.seed if a.n == 1 else 0)
        img.resize(final, Image.LANCZOS).save(path)
        path.with_suffix(path.suffix + ".prompt.txt").write_text(
            f"model: flux.1-dev (NVIDIA API)\naspect: {a.aspect}  steps: {a.steps}  cfg: {a.cfg}\n"
            f"seed: {seed}   (reproduce with --seed {seed})\n\n{prompt}\n")
        print(f"background -> {path}  ({final[0]}x{final[1]}, seed {seed})")


if __name__ == "__main__":
    main()
