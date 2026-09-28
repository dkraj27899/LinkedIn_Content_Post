"""
nano_banana.py — GoalFi-branded LinkedIn visuals with Google's Nano Banana (Gemini image models).
(Run every command from the GoalFi LinkedIn Studio root folder.)

  # single image (4:5 portrait is LinkedIn's best-performing feed format)
  python3.12 scripts/nano_banana.py --prompt-file posts/<slug>/image_prompt.md --out posts/<slug>/image.png

  # use a matplotlib chart as the layout/number reference, 3 variants to pick from
  python3.12 scripts/nano_banana.py --prompt-file ... --ref posts/<slug>/chart.png --n 3 --out posts/<slug>/image.png

  # carousel: one prompt file per slide, then stitch into the PDF LinkedIn wants
  python3.12 scripts/nano_banana.py --prompt-file posts/<slug>/slide1.md --out posts/<slug>/slides/01.png
  python3.12 scripts/nano_banana.py --pdf posts/<slug>/slides/*.png --out posts/<slug>/carousel.pdf

  # edit an image ("make the headline bigger", "fix 4,530 -> 4,531") — always edit the
  # logo-free master (<name>.raw.png); the real logo is re-stamped on the result
  python3.12 scripts/nano_banana.py --edit posts/<slug>/image.raw.png --prompt "..." --out posts/<slug>/image_v2.png

Design rules this script enforces:
  * GoalFi brand preamble (navy #172554 + gold #d29900) is prepended to every prompt.
  * The real GoalFi logo is stamped on AFTER generation with PIL — never drawn by the model
    (image models distort logos). The prompt reserves the corner for it.
  * Every run saves <out>.prompt.txt next to the image, so any published visual is reproducible.
  * Image models can garble numbers. After generating, READ the PNG and check every figure
    against facts.json. If a number is wrong after 2 edits, fall back to a matplotlib chart.

Key: GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment or in <studio root>/.env
Model: NANO_BANANA_MODEL env or --model. Default = Nano Banana Pro (best text rendering).
"""
import argparse
import glob
import os
import sys
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

import _env

ROOT = Path(__file__).resolve().parent.parent          # GoalFi LinkedIn Studio/
LOGO_ON_DARK = ROOT / "assets/logos/logo_on_dark.png"    # white + gold
LOGO_ON_LIGHT = ROOT / "assets/logos/logo_on_light.png"  # navy + gold

MODELS = {
    "pro": "gemini-3-pro-image-preview",   # Nano Banana Pro — sharper text, better infographics
    "fast": "gemini-2.5-flash-image",      # Nano Banana — cheaper/faster drafts
}
DEFAULT_MODEL = os.environ.get("NANO_BANANA_MODEL", MODELS["pro"])

BRAND = """You are designing a premium LinkedIn data graphic for GoalFi, an Indian mutual-fund
research & wealth platform. Audience: Indian investors, advisors and finance professionals.

BRAND (mandatory):
- Palette: deep navy #172554 (primary background or headline colour), gold #d29900 (accents,
  key numbers, highlights), white/off-white #F4F6FA, slate #33507D for secondary text.
  Semantic: green #16A34A = buying/positive, red #B42318 = selling/negative. No other hues.
- Style: clean institutional research look (think Goldman Sachs / Bloomberg chart pack), flat
  vector, generous whitespace, crisp sans-serif typography (Inter / Manrope feel), subtle grid.
- NO stock photos, NO people, NO 3D clip-art, NO emojis, NO currency-note imagery, NO fake logos.
- Do NOT draw any logo or the word "GoalFi" as a logo. Leave the {corner} corner
  (about 22% width x 9% height) completely empty — the real logo is added afterwards.
- Every number and label must be rendered EXACTLY as written below — same digits, commas,
  ₹ symbol, % signs and decimals. Do not invent, round, or add any number not given.
- Put this footer text small at the bottom-left: "{footer}"
- Text must be large enough to read on a phone. Maximum ~40 words of text on the image.

CONTENT:
"""

DEFAULT_FOOTER = "Source: AMC monthly portfolio disclosures (SEBI) · GoalFi analysis"


def load_key():
    key = _env.get("GEMINI_API_KEY") or _env.get("GOOGLE_API_KEY")
    if not key:
        sys.exit("No GEMINI_API_KEY. Put it in 'GoalFi LinkedIn Studio/.env' (see .env.example). "
                 "Get one at https://aistudio.google.com/apikey")
    return key


def client():
    from google import genai
    return genai.Client(api_key=load_key())


def _images_from(resp):
    out = []
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else []) or []:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                out.append(Image.open(BytesIO(part.inline_data.data)).convert("RGB"))
    return out


def generate(prompt, refs=(), aspect="4:5", size="2K", model=DEFAULT_MODEL, retries=3):
    from google.genai import types
    contents = [prompt] + [Image.open(r) for r in refs]
    img_cfg = {"aspect_ratio": aspect}
    if "pro" in model or "3" in model:
        img_cfg["image_size"] = size          # Pro supports 1K / 2K / 4K
    cfg = types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(**img_cfg))
    last = None
    for attempt in range(retries):
        try:
            imgs = _images_from(client().models.generate_content(model=model, contents=contents, config=cfg))
            if imgs:
                return imgs[0]
            last = "model returned no image (possibly a safety block — simplify the prompt)"
        except Exception as e:  # rate limits / transient 5xx
            last = e
        time.sleep(4 * (attempt + 1))
    sys.exit(f"Generation failed after {retries} tries: {last}")


def stamp_logo(img, corner="top-right", width_frac=0.20, margin_frac=0.045):
    W, H = img.size
    m = int(W * margin_frac)
    lw = int(W * width_frac)
    # Pick the logo variant by the brightness of the corner it will sit on
    box_h = int(lw * 748 / 2000)
    x = W - lw - m if "right" in corner else m
    y = m if "top" in corner else H - box_h - m
    patch = img.crop((x, y, x + lw, y + box_h)).convert("L")
    dark = sum(patch.getdata()) / (lw * box_h) < 128
    logo = Image.open(LOGO_ON_DARK if dark else LOGO_ON_LIGHT).convert("RGBA")
    logo = logo.resize((lw, int(lw * logo.height / logo.width)), Image.LANCZOS)
    out = img.convert("RGBA")
    out.alpha_composite(logo, (x, y))
    return out.convert("RGB")


def to_pdf(pngs, out):
    pages = [Image.open(p).convert("RGB") for p in sorted(pngs)]
    if not pages:
        sys.exit("no slides found")
    pages[0].save(out, save_all=True, append_images=pages[1:], resolution=300, quality=95, subsampling=0)  # crisp text
    print(f"carousel -> {out} ({len(pages)} slides)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", help="content prompt text")
    ap.add_argument("--prompt-file", help="file holding the content prompt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", action="append", default=[], help="reference image(s): chart, layout sketch")
    ap.add_argument("--edit", help="existing image to modify with --prompt")
    ap.add_argument("--aspect", default="4:5", choices=["4:5", "1:1", "16:9", "9:16", "3:4", "4:3"])
    ap.add_argument("--size", default="2K", choices=["1K", "2K", "4K"])
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"model id or alias {list(MODELS)}")
    ap.add_argument("--n", type=int, default=1, help="number of variants")
    ap.add_argument("--corner", default="top-right", choices=["top-right", "top-left", "bottom-right", "bottom-left"])
    ap.add_argument("--footer", default=DEFAULT_FOOTER)
    ap.add_argument("--no-brand", action="store_true", help="skip brand preamble (raw prompt)")
    ap.add_argument("--no-logo", action="store_true")
    ap.add_argument("--pdf", nargs="+", help="stitch slide PNGs into a carousel PDF (use with --out x.pdf)")
    a = ap.parse_args()

    if a.pdf:
        files = [f for p in a.pdf for f in (glob.glob(p) or [p])]
        return to_pdf(files, a.out)

    model = MODELS.get(a.model, a.model)
    body = Path(a.prompt_file).read_text() if a.prompt_file else (a.prompt or "")
    if not body.strip():
        sys.exit("give --prompt or --prompt-file")
    if a.edit:
        if a.edit.endswith(".png") and not a.edit.endswith(".raw.png") and Path(a.edit[:-4] + ".raw.png").exists():
            print("note: editing the logo-free master", a.edit[:-4] + ".raw.png")
            a.edit = a.edit[:-4] + ".raw.png"
        prompt = ("Edit this image. Keep the layout, brand colours, fonts and every number not "
                  "mentioned below exactly as they are. Keep the logo corner empty/unchanged.\n\n" + body)
        refs = [a.edit] + a.ref
    else:
        prompt = body if a.no_brand else BRAND.format(corner=a.corner, footer=a.footer) + body
        refs = a.ref

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for k in range(a.n):
        path = out if a.n == 1 else out.with_name(f"{out.stem}_v{k + 1}{out.suffix}")
        img = generate(prompt, refs, a.aspect, a.size, model)
        img.save(path.with_suffix(".raw.png"))          # logo-free master, use this for --edit
        if not a.no_logo:
            img = stamp_logo(img, a.corner)
        img.save(path)
        path.with_suffix(path.suffix + ".prompt.txt").write_text(
            f"model: {model}\naspect: {a.aspect}  size: {a.size}\nrefs: {refs}\n\n{prompt}\n")
        print(f"image -> {path}  ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
