"""
brand_chart.py — GoalFi-branded slides drawn by code, so every number is exact.
(Run every command from the GoalFi LinkedIn Studio root folder.)

Two slide kinds, both 4:5, rendered at --scale x 1080x1350 (default 2 = 2160x2700, ultra sharp):
  * "bars"  — horizontal bar chart (optionally with a right-hand tag column, e.g. YTD return)
  * "cover" — carousel cover: kicker, big headline, stat tiles, swipe cue

  python3.12 scripts/brand_chart.py --data posts/<slug>/chart.json --out posts/<slug>/chart.png
  python3.12 scripts/brand_chart.py --data posts/<slug>/slide1.json --background posts/<slug>/bg.png --out posts/<slug>/slides/01.png

bars spec:
{
  "kind": "bars",
  "kicker": "GOALFI RESEARCH · 2/3",                 # small caps line above the title (optional)
  "title": "What mutual funds bought in August 2026",
  "subtitle": "Net buying by active equity schemes",
  "bars": [                                           # top to bottom, as they should appear
    {"label": "Bank of India\\nSmall Cap", "value": 32.25},
    {"label": "Nifty 50 index fund", "value": -10.73, "color": "#64748B"},   # per-bar colour override
    {"label": "SBI Nifty 50 ETF", "value": 213804.39, "tag": -10.63}          # tag -> right column
  ],
  "format":     {"prefix": "", "suffix": "%", "decimals": 2, "signed": true},   # bar value labels
  "tag_format": {"suffix": "%", "decimals": 2, "signed": true},                 # right column
  "tag_header": "YTD return",
  "tag_color": "#33507D",      # optional fixed colour for the tag column (default: green/red by sign)
  "colors": "signed",          # "signed" = green/red by sign; "brand" = navy bars
  "separator_before": 10,      # optional thin rule before bar index N (e.g. before a benchmark)
  "note": "...", "footer": "..."
}
cover spec:
{
  "kind": "cover", "kicker": "...", "title": "...", "subtitle": "...",
  "stats": [{"value": "−10.73%", "label": "Nifty 50 index fund", "tone": "red|green|gold"}],
  "cta": "Swipe →", "footer": "..."
}
Values print exactly as given: Indian digit grouping, true minus sign (−), fixed decimals.
"""
import argparse
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.transforms import blended_transform_factory  # noqa: E402
from PIL import Image  # noqa: E402

from nano_banana import DEFAULT_FOOTER, stamp_logo  # noqa: E402

NAVY, GOLD, BG, SLATE, GREEN, RED = "#172554", "#d29900", "#F4F6FA", "#33507D", "#16A34A", "#B42318"
GREY, INK, LIGHT = "#64748B", "#0F172A", "#DCE4F2"
TONES = {"red": "#F87171", "green": "#4ADE80", "gold": "#F2B632", "white": "white"}   # on navy
BASE_PX = (1080, 1350)
DPI = 150

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
for f in FONT_DIR.glob("Inter-*.ttf"):
    font_manager.fontManager.addfont(str(f))
plt.rcParams["font.family"] = ["Inter", "DejaVu Sans"]


def inr(v, decimals=2):
    """Indian grouping with fixed decimals: 213804.39 -> 2,13,804.39 ; true minus sign."""
    s = f"{abs(v):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        whole = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", whole[:-3]) + "," + whole[-3:]
    return ("−" if v < 0 else "") + whole + (f".{frac}" if frac else "")


def fmt(v, f=None):
    f = {"prefix": "", "suffix": "", "decimals": 2, "signed": False, **(f or {})}
    body = inr(v, f["decimals"])
    if f["signed"] and v > 0:
        body = "+" + body
    if body.startswith("−"):                       # keep sign before the prefix: −₹5 not ₹−5
        return "−" + f["prefix"] + body[1:] + f["suffix"]
    return f["prefix"] + body + f["suffix"]


def _cover_crop(img, size):
    """Scale + centre-crop an image to exactly `size`."""
    W, H = size
    r = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))


def _scrim(img, top=0.34, strength=0.80, bottom=0.0):
    """Navy gradient over the top (and optionally the bottom) so white text stays readable."""
    W, H = img.size
    col = Image.new("L", (1, H), 0)
    px = col.load()
    t, b = int(H * top), int(H * bottom)
    for y in range(H):
        a = 0.0
        if y < t:
            a = strength * (1 - y / t) ** 1.3
        if b and y > H - b:
            a = max(a, strength * ((y - (H - b)) / b) ** 1.3)
        px[0, y] = int(255 * a)
    mask = col.resize((W, H))
    navy = Image.new("RGBA", (W, H), (23, 37, 84, 255))
    navy.putalpha(mask)
    return Image.alpha_composite(img.convert("RGBA"), navy)


def _figure(size, scale, on_bg):
    fig = plt.figure(figsize=(size[0] / DPI, size[1] / DPI), dpi=DPI * scale,
                     facecolor="none" if on_bg else BG)
    return fig


def _header(fig, spec, on_bg, y_title=0.905):
    head, sub, kick = ("white", LIGHT, TONES["gold"]) if on_bg else (NAVY, SLATE, GOLD)
    if spec.get("kicker"):
        fig.text(0.07, y_title + 0.047, spec["kicker"].upper(), fontsize=8.5, color=kick,
                 fontweight="semibold")
    fig.text(0.07, y_title, spec["title"], fontsize=19, fontweight="bold", color=head)
    if spec.get("subtitle"):
        fig.text(0.07, y_title - 0.037, spec["subtitle"], fontsize=10.5, color=sub)


def render_bars(spec, size, scale, on_bg):
    bars = [b if isinstance(b, dict) else {"label": b[0], "value": b[1], **({"tag": b[2]} if len(b) > 2 else {})}
            for b in spec["bars"]]
    bars = bars[::-1]                                     # matplotlib draws bottom-up
    n = len(bars)
    vals = [b["value"] for b in bars]
    has_tags = any("tag" in b for b in bars)
    fig = _figure(size, scale, on_bg)
    card = (0.05, 0.03, 0.90, 0.80)
    if on_bg:
        fig.patches.append(FancyBboxPatch(card[:2], card[2], card[3],
                                          boxstyle="round,pad=0,rounding_size=0.018",
                                          transform=fig.transFigure, facecolor=BG, alpha=0.975,
                                          edgecolor="none", zorder=0))
    _header(fig, spec, on_bg)
    right = 0.73 if has_tags else 0.92
    ax = fig.add_axes([0.335, 0.125, right - 0.335, 0.675], facecolor="none", zorder=1)
    mode = spec.get("colors", "signed")

    def colour(b):
        if b.get("color"):
            return b["color"]
        if mode == "brand":
            return NAVY
        return GREEN if b["value"] >= 0 else RED

    ax.barh(range(n), vals, color=[colour(b) for b in bars], height=0.66, zorder=2)
    span = max(abs(v) for v in vals) or 1
    lo, hi = min(0, min(vals)), max(0, max(vals))
    for i, b in enumerate(bars):
        v = b["value"]
        x = (v if v >= 0 else 0) + 0.018 * span
        ax.text(x, i, fmt(v, spec.get("format")), va="center", ha="left", fontsize=9.5,
                color=colour(b) if (v < 0 or b.get("color")) else INK, fontweight="bold", zorder=3)
    ax.set_xlim(lo * 1.05 if lo < 0 else 0, max(hi, 0.25 * span) + (0.42 if hi > 0 else 0.6) * span)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_yticks(range(n))
    ax.set_yticklabels([b["label"] for b in bars], fontsize=9.5, color=INK, linespacing=1.15)
    ax.tick_params(axis="y", length=0, pad=8)
    ax.set_xticks([])
    if lo < 0:
        ax.axvline(0, color=GREY, lw=0.8, zorder=1)
    for s in ax.spines.values():
        s.set_visible(False)
    # zebra rows across the full card width, so labels, bars and the tag column line up
    row_tr = blended_transform_factory(fig.transFigure, ax.transData)
    for i in range(n):
        if i % 2 == 0:
            ax.add_patch(Rectangle((0.065, i - 0.5), 0.87, 1, transform=row_tr, facecolor="#E8EDF5",
                                   edgecolor="none", zorder=0, clip_on=False))
    sep = spec.get("separator_before")
    if sep is not None:
        y = (n - sep) - 0.5                                # boundary above display row `sep`
        tr = blended_transform_factory(fig.transFigure, ax.transData)
        ax.plot([0.07, 0.93], [y, y], transform=tr, color=GREY, lw=0.8, ls=(0, (3, 3)), clip_on=False, zorder=4)
    if has_tags:
        tr = blended_transform_factory(fig.transFigure, ax.transData)
        tf = {"suffix": "%", "decimals": 2, "signed": True, **(spec.get("tag_format") or {})}
        for i, b in enumerate(bars):
            if "tag" in b:
                t = b["tag"]
                tc = spec.get("tag_color") or (GREEN if t > 0 else (RED if t < 0 else GREY))
                ax.text(0.925, i, fmt(t, tf), transform=tr, va="center", ha="right", fontsize=9.5,
                        fontweight="bold", color=tc, zorder=3)
        ax.text(0.925, n - 0.35, spec.get("tag_header", ""), transform=tr, va="bottom", ha="right",
                fontsize=8, color=GREY, fontweight="semibold")
    if spec.get("note"):
        fig.text(0.075, 0.072, spec["note"], fontsize=7.6, color=SLATE, linespacing=1.35, va="bottom")
    fig.text(0.075, 0.045, spec.get("footer", DEFAULT_FOOTER), fontsize=7.6, color=GREY)
    return fig


def render_cover(spec, size, scale, on_bg):
    fig = _figure(size, scale, on_bg)
    head, sub = ("white", LIGHT) if on_bg else (NAVY, SLATE)
    if spec.get("kicker"):
        fig.text(0.08, 0.80, spec["kicker"].upper(), fontsize=10, color=TONES["gold"] if on_bg else GOLD,
                 fontweight="semibold")
    fig.text(0.08, 0.775, spec["title"], fontsize=31, fontweight="extra bold", color=head,
             va="top", linespacing=1.08)
    if spec.get("subtitle"):
        fig.text(0.08, spec.get("subtitle_y", 0.655), spec["subtitle"], fontsize=12.5, color=sub,
                 va="top", linespacing=1.4)
    stats = spec.get("stats", [])
    if stats:
        gap, x0, w_total = 0.022, 0.08, 0.84
        w = (w_total - gap * (len(stats) - 1)) / len(stats)
        y, h = 0.20, 0.19
        for k, st in enumerate(stats):
            x = x0 + k * (w + gap)
            fig.patches.append(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.015",
                                              transform=fig.transFigure, facecolor=(0.07, 0.11, 0.25, 0.80),
                                              edgecolor=(1, 1, 1, 0.22), linewidth=0.8))
            fig.patches.append(Rectangle((x + 0.02, y + h - 0.012), w * 0.28, 0.004,
                                         transform=fig.transFigure, facecolor=TONES["gold"], edgecolor="none"))
            fig.text(x + 0.02, y + h - 0.035, st["value"], fontsize=21, fontweight="bold",
                     color=TONES.get(st.get("tone", "white"), "white"), va="top")
            fig.text(x + 0.02, y + 0.022, st["label"], fontsize=8.6, color=LIGHT, va="bottom",
                     linespacing=1.3, wrap=True)
    if spec.get("cta"):
        fig.text(0.92, 0.105, spec["cta"], fontsize=11, color=TONES["gold"], ha="right", fontweight="semibold")
    fig.text(0.08, 0.045, spec.get("footer", DEFAULT_FOOTER), fontsize=7.6, color=LIGHT if on_bg else GREY)
    return fig


def _shade(hex_color, f):
    """f > 0 lightens toward white, f < 0 darkens toward black."""
    r, g, b = matplotlib.colors.to_rgb(hex_color)
    t = (1, 1, 1) if f > 0 else (0, 0, 0)
    f = abs(f)
    return tuple(c + (tc - c) * f for c, tc in zip((r, g, b), t))


def _soft_shadow(ax, x, y, w, h, r, dx=5, dy=7, layers=6, alpha=0.035, spread=2.2):
    """Blurred drop shadow: stacked, progressively larger translucent rounded rects."""
    for k in range(layers):
        g = k * spread
        ax.add_patch(FancyBboxPatch((x + dx - g, y + dy - g), w + 2 * g, h + 2 * g,
                                    boxstyle=f"round,pad=0,rounding_size={r + g}",
                                    facecolor=(0.04, 0.07, 0.18, alpha), edgecolor="none", zorder=1))


def _bar3d(ax, x0, yc, length, h, base, depth=9):
    """Crystal-style 3D horizontal bar: gradient front, lit top face, shaded end, gloss, shadow."""
    from matplotlib.patches import Polygon
    import numpy as np
    x1, yt, yb = x0 + length, yc - h / 2, yc + h / 2
    _soft_shadow(ax, x0, yt, length + depth, h, 4, dx=4, dy=8, layers=5, alpha=0.05, spread=1.8)
    # top face (extruded up-right) and end face
    ax.add_patch(Polygon([(x0, yt), (x1, yt), (x1 + depth, yt - depth), (x0 + depth, yt - depth)],
                         closed=True, facecolor=_shade(base, 0.42), edgecolor="none", zorder=3))
    ax.add_patch(Polygon([(x1, yt), (x1, yb), (x1 + depth, yb - depth), (x1 + depth, yt - depth)],
                         closed=True, facecolor=_shade(base, -0.28), edgecolor="none", zorder=3))
    # front face: vertical gradient, clipped to the bar rectangle
    stops = np.array([_shade(base, 0.30), _shade(base, 0.08), matplotlib.colors.to_rgb(base), _shade(base, -0.18)])
    t = np.linspace(0, 1, 64)
    grad = np.stack([np.interp(t, [0, 0.35, 0.6, 1], stops[:, c]) for c in range(3)], axis=1)
    img = ax.imshow(grad[:, None, :], extent=(x0, x1, yb, yt), aspect="auto", zorder=4,
                    interpolation="bicubic")
    clip = Rectangle((x0, yt), length, h, transform=ax.transData)
    img.set_clip_path(clip)
    # gloss band + crisp edge
    ax.add_patch(Rectangle((x0, yt + 1.5), length, h * 0.36, facecolor=(1, 1, 1, 0.22), edgecolor="none", zorder=5))
    ax.add_patch(Rectangle((x0, yt), length, h, facecolor="none", edgecolor=_shade(base, -0.35), lw=0.4, zorder=5))
    return x1 + depth


def render_ranking(spec, size, scale, on_bg):
    """
    Premium ranking slide: rank · AMC logo plate · 3D value bar · exact label · right-hand metric.
    Coordinates are base pixels (1080 x 1350, y down) on one full-figure axes.
    """
    W, H = size
    fig = _figure(size, scale, on_bg)
    fig._logos = []
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    ax.set_facecolor("none")
    head, sub, kick = ("white", LIGHT, TONES["gold"]) if on_bg else (NAVY, SLATE, GOLD)

    # header
    if spec.get("kicker"):
        ax.text(62, 78, spec["kicker"].upper(), fontsize=8.5, color=kick, fontweight="semibold", va="baseline")
    ax.text(60, 128, spec["title"], fontsize=21, color=head, fontweight="bold", va="baseline")
    if spec.get("subtitle"):
        ax.text(62, 168, spec["subtitle"], fontsize=10.5, color=sub, va="baseline")

    # card
    cx0, cy0, cx1, cy1 = 30, 205, W - 30, H - 32
    _soft_shadow(ax, cx0, cy0, cx1 - cx0, cy1 - cy0, 22, dx=0, dy=10, layers=8, alpha=0.05, spread=3)
    ax.add_patch(FancyBboxPatch((cx0, cy0), cx1 - cx0, cy1 - cy0, boxstyle="round,pad=0,rounding_size=22",
                                facecolor="#F7F9FC", edgecolor=(1, 1, 1, 0.9), lw=1, zorder=2))

    rows = spec["rows"]
    n = len(rows)
    col_rank, plate_x, plate_w, plate_h = 70, 104, 190, 60
    bar_x0, bar_len = 322, spec.get("bar_len", 430)
    right_x = cx1 - 26
    top, bottom = 290, cy1 - 118
    row_h = (bottom - top) / n
    # column headers
    hdr = dict(fontsize=7.4, color=GREY, fontweight="semibold", va="baseline", zorder=6)
    ax.text(col_rank, 258, "#", ha="center", **hdr)
    ax.text(plate_x + 6, 258, spec.get("name_header", "FUND HOUSE"), **hdr)
    ax.text(bar_x0, 258, spec.get("value_header", "").upper(), **hdr)
    if spec.get("tag_header"):
        ax.text(right_x, 258, spec["tag_header"].upper(), ha="right", **hdr)
    ax.plot([cx0 + 22, cx1 - 22], [272, 272], color="#D8DFEA", lw=0.8, zorder=6)

    vals = [r["value"] for r in rows]
    vmax = max(vals) or 1
    fmt_v, fmt_t = spec.get("format"), {"decimals": 2, **(spec.get("tag_format") or {})}
    for i, r in enumerate(rows):
        yc = top + row_h * (i + 0.5)
        hl = r.get("highlight")
        if i % 2 == 0 or hl:
            ax.add_patch(FancyBboxPatch((cx0 + 14, yc - row_h / 2 + 3), cx1 - cx0 - 28, row_h - 6,
                                        boxstyle="round,pad=0,rounding_size=12",
                                        facecolor="#FFF6DD" if hl else "#EEF2F8",
                                        edgecolor=GOLD if hl else "none", lw=1.1 if hl else 0, zorder=2.5))
        # rank
        rank = r.get("rank", i + 1)
        ax.text(col_rank, yc, f"{rank:02d}", ha="center", va="center", fontsize=13, fontweight="bold",
                color=GOLD if rank == 1 else NAVY, zorder=6)
        # logo plate
        py = yc - plate_h / 2
        _soft_shadow(ax, plate_x, py, plate_w, plate_h, 10, dx=0, dy=3, layers=4, alpha=0.04, spread=1.5)
        ax.add_patch(FancyBboxPatch((plate_x, py), plate_w, plate_h, boxstyle="round,pad=0,rounding_size=10",
                                    facecolor="white", edgecolor="#DCE3EE", lw=0.8, zorder=5))
        logo = r.get("logo")
        if logo and Path(logo).exists():
            # Pasted after rendering by _paste_logos at exact pixels: matplotlib's resampling
            # smears small transparent logos.
            fig._logos.append((logo, plate_x + 12, py + 8, plate_w - 24, plate_h - 16))
        else:
            ax.text(plate_x + plate_w / 2, yc, r.get("name", "?"), ha="center", va="center", fontsize=9,
                    fontweight="bold", color=NAVY, zorder=6)
        # 3D bar
        base = r.get("color") or (GOLD if hl else spec.get("bar_color", GREEN))
        length = max(bar_len * r["value"] / vmax, 6)
        end = _bar3d(ax, bar_x0, yc + 3, length, 30, base)
        ax.text(end + 10, yc + 3, fmt(r["value"], fmt_v) + r.get("mark", ""), va="center", ha="left", fontsize=12,
                fontweight="bold", color=_shade(GOLD, -0.25) if hl else INK, zorder=6)
        # right-hand metric
        if "tag" in r:
            t = r["tag"]
            tc = spec.get("tag_color") or (GREEN if t > 0 else (RED if t < 0 else GREY))
            ax.text(right_x, yc + 3, fmt(t, fmt_t), va="center", ha="right", fontsize=11,
                    fontweight="semibold", color=tc, zorder=6)

    # notes + source inside the card
    y = cy1 - 84
    if spec.get("note"):
        ax.text(cx0 + 30, y, spec["note"], fontsize=7.6, color=SLATE, va="top", linespacing=1.45, zorder=6)
    ax.text(cx0 + 30, cy1 - 22, spec.get("footer", DEFAULT_FOOTER), fontsize=7.4, color=GREY, va="baseline", zorder=6)
    return fig


def _paste_logos(img, logos, scale):
    """Paste logos into their boxes (base px) at the final resolution: one LANCZOS resize, no smear."""
    img = img.convert("RGBA")
    for path, x, y, bw, bh in logos:
        im = Image.open(path).convert("RGBA")
        k = min(bw * scale / im.width, bh * scale / im.height)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        px = round(x * scale + (bw * scale - im.width) / 2)
        py = round(y * scale + (bh * scale - im.height) / 2)
        img.alpha_composite(im, (px, py))
    return img


def render(spec, out, size=BASE_PX, logo=True, background=None, scale=2):
    on_bg = background is not None
    kind = spec.get("kind", "bars")
    fig = {"cover": render_cover, "ranking": render_ranking}.get(kind, render_bars)(spec, size, scale, on_bg)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI * scale, facecolor=fig.get_facecolor(), transparent=on_bg)
    logos = getattr(fig, "_logos", [])
    plt.close(fig)
    img = Image.open(out)
    if on_bg:
        base = _cover_crop(Image.open(background).convert("RGB"), img.size)
        if kind in ("bars", "ranking"):                   # navy gradient behind the white header
            base = _scrim(base, top=0.30, strength=0.82)
        else:                                             # even navy wash so the whole cover reads
            base = Image.alpha_composite(base.convert("RGBA"),
                                         Image.new("RGBA", base.size, (23, 37, 84, int(255 * 0.45))))
        img = Image.alpha_composite(base, img.convert("RGBA"))
    if logos:
        img = _paste_logos(img, logos, scale)
    img = img.convert("RGB")
    if logo:
        img = stamp_logo(img, "top-right", width_frac=0.20 if kind == "cover" else 0.17)
    img.save(out, optimize=True)
    print(f"{kind} -> {out}  ({img.size[0]}x{img.size[1]})" + (f"  on {background}" if on_bg else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--square", action="store_true", help="1080x1080 instead of 1080x1350")
    ap.add_argument("--scale", type=float, default=2, help="2 = 2160x2700 (default, ultra sharp)")
    ap.add_argument("--no-logo", action="store_true")
    ap.add_argument("--background", help="background image (e.g. from flux_nvidia.py)")
    a = ap.parse_args()
    render(json.loads(Path(a.data).read_text()), a.out, (1080, 1080) if a.square else BASE_PX,
           not a.no_logo, a.background, a.scale)
