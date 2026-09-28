"""
amc_logos.py — cache every AMC's official logo locally, as crisp high-res PNGs.
(Run every command from the GoalFi LinkedIn Studio root folder.)

Source: MUTUALFUND_DATA.AMCDirectory (loaded by MF Tool/AMFIAmcDirectory.py), the same
AMFI-hosted assets the GoalFi Tracking portal's <AmcLogo> uses: `icons[0]` (square) and
`icon_wordmark` (wide). Most are SVG, so they are rasterised at 512 px for sharp slides.

  python3.12 scripts/amc_logos.py            # fetch / refresh all AMCs
  python3.12 scripts/amc_logos.py --check    # list what's cached

Output: assets/amc_logos/<slug>_{icon,wordmark}.png + index.json keyed by mf_name.
Logos are third-party trademarks: assets/amc_logos/ is gitignored, never commit it.
Use them only to identify the AMC next to its own data (nominative use).
"""
import argparse
import base64
import io
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image

import _env

_BREW = "/opt/homebrew/lib"


def _ensure_cairo():
    """cairosvg needs Homebrew's libcairo, and dyld reads its search path only at process start,
    so when run as a script without it, relaunch once with the path set. Importers of logo_for()
    never reach this."""
    if sys.platform == "darwin" and _BREW not in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", ""):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = _BREW + ":" + os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        os.execv(sys.executable, [sys.executable] + sys.argv)

OUT = _env.ROOT / "assets" / "amc_logos"
TARGET_PX = 512

# "badge" = the variant that reads best in a chart row. Default: the wordmark.
# Crops are fractions of the chosen image (left, top, right, bottom), applied before trimming.
BADGE = {
    "Aditya Birla Sun Life Mutual Fund": ("icon", None),        # wordmark is a text block
    "Samco Mutual Fund": ("wordmark", (0, 0, 0.445, 1)),        # drop the tagline after the divider
}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _masked_bitmap(svg):
    """Some AMFI 'SVGs' are a colour PNG + greyscale mask PNG in a wrapper (Bank of India).
    cairosvg ignores the luminance mask and renders black, so composite them directly."""
    text = svg.decode("utf-8", "ignore")
    if "<mask" not in text:
        return None
    pngs = [Image.open(io.BytesIO(base64.b64decode(b)))
            for b in re.findall(r'data:image/png;base64,([^"\']+)', text)]
    mask = next((i for i in pngs if i.mode == "L"), None)
    colour = next((i for i in pngs if i.mode in ("RGB", "RGBA") and mask and i.size == mask.size), None)
    if not (mask and colour):
        return None
    im = colour.convert("RGBA")
    im.putalpha(mask)
    return im


def _trim(im):
    """Crop to content, ignoring both transparent and near-white margins."""
    flat = Image.new("RGBA", im.size, (255, 255, 255, 255))
    flat.alpha_composite(im)
    ink = flat.convert("L").point(lambda v: 255 if v < 245 else 0)
    box = ink.getbbox()
    return im.crop(box) if box else im


def to_png(raw, crop=None):
    """SVG or bitmap bytes -> RGBA image, trimmed to content, longest side TARGET_PX."""
    im = None
    if raw[:5] == b"<?xml" or b"<svg" in raw[:400]:
        im = _masked_bitmap(raw)
        if im is None:
            import cairosvg
            raw = cairosvg.svg2png(bytestring=raw, output_width=TARGET_PX * 2)
    if im is None:
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
    im = _trim(im)
    if crop:
        W, H = im.size
        im = _trim(im.crop((int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H))))
    r = TARGET_PX / max(im.size)
    if r < 1:                                   # never upscale bitmaps (it only blurs)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    return im


def fetch_all():
    import requests
    from pymongo import MongoClient
    OUT.mkdir(parents=True, exist_ok=True)
    col = MongoClient(_env.get("MF_MONGO_URI"), serverSelectionTimeoutMS=30000).MUTUALFUND_DATA.AMCDirectory
    index = {}
    for d in col.find({}, {"mf_name": 1, "icons": 1, "icon_wordmark": 1}):
        name = d.get("mf_name")
        if not name:
            continue
        entry, raws = {}, {}
        for kind, url in (("icon", (d.get("icons") or [{}])[0].get("url")),
                          ("wordmark", (d.get("icon_wordmark") or {}).get("url"))):
            if not url:
                continue
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
                r.raise_for_status()
                raws[kind] = r.content
                im = to_png(r.content)
                path = OUT / f"{slug(name)}_{kind}.png"
                im.save(path)
                entry[kind] = {"path": str(path.relative_to(_env.ROOT)), "size": im.size, "source": url}
            except Exception as e:
                entry[kind + "_error"] = str(e)[:120]
        kind, crop = BADGE.get(name, ("wordmark", None))
        if kind not in raws:
            kind = next(iter(raws), None)
        if kind:
            im = to_png(raws[kind], crop)
            path = OUT / f"{slug(name)}_badge.png"
            im.save(path)
            entry["badge"] = {"path": str(path.relative_to(_env.ROOT)), "size": im.size, "from": kind}
        index[name] = entry
        print(f"{name:42} icon={entry.get('icon', {}).get('size')} wordmark={entry.get('wordmark', {}).get('size')}"
              + (f"  ERR {entry}" if any(k.endswith('_error') for k in entry) else ""))
    (OUT / "index.json").write_text(json.dumps(index, indent=2))
    print(f"\n{len(index)} AMCs -> {OUT}/index.json")


def logo_for(fund_house, kind="badge"):
    """Path to a cached logo for an AMC name as it appears in MFDetails / NAV data, else None."""
    idx = json.loads((OUT / "index.json").read_text()) if (OUT / "index.json").exists() else {}
    norm = lambda s: re.sub(r"\b(mutual fund|mf|asset management|amc)\b|[^a-z0-9]", "", s.lower())
    for name, e in idx.items():
        if norm(name) == norm(fund_house):
            got = e.get(kind) or e.get("icon") or e.get("wordmark")
            return str(_env.ROOT / got["path"]) if got else None
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        _ensure_cairo()
    if a.check:
        for n, e in json.loads((OUT / "index.json").read_text()).items():
            print(f"{n:42} {e.get('icon', {}).get('size')}  {e.get('wordmark', {}).get('size')}")
    else:
        fetch_all()
