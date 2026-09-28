# GoalFi LinkedIn Studio — CLAUDE.md

## What this folder is

The production line for GoalFi's LinkedIn content built on our Indian mutual-fund holdings
data. Every month all 52 AMCs publish full scheme portfolios; the MF Tool pipeline parses them
into `MUTUALFUND_DATA.MFDetails` (2.18M holdings, Jan 2025 onward). This folder turns that data
into posts: **cleaned facts → post copy → branded visual (NVIDIA FLUX background + exact chart, or Nano Banana) → user publishes**.

The step-by-step workflow is the **`mf-linkedin-post` skill** in
`.claude/skills/mf-linkedin-post/SKILL.md`. It is symlinked from `~/.claude/skills/`, so it
works from any project. Always follow it. This file holds the standing rules and reference.

**Run every command from this folder's root** (`/Users/dikshant/GOALFI_MAIN/GoalFi LinkedIn Studio`).

## Structure

```
GoalFi LinkedIn Studio/
├── CLAUDE.md                        standing rules (this file)
├── MEMORY.md                        running memory: post log, voice feedback, caveats, backlog
├── .env                             MF_MONGO_URI, NVIDIA_API_KEY, GEMINI_API_KEY (from .env.example; gitignored)
├── .env.example
├── .gitignore
├── .claude/skills/mf-linkedin-post/
│   └── SKILL.md                     the 8-step post workflow
├── scripts/
│   ├── mf_facts.py                  ONLY source of numbers: months|health|top|flows|sectors|caps|stock
│   ├── flux_nvidia.py               FLUX.1-dev (NVIDIA API) text-free background art, seed saved
│   ├── brand_chart.py               exact-number slides (bars / cover), 2× render, --background onto FLUX art
│   ├── amc_logos.py                 caches all 57 AMC logos from MUTUALFUND_DATA.AMCDirectory (AMFI assets)
│   ├── nano_banana.py               Gemini image gen (optional route), --edit/--ref/--n, --pdf carousels
│   └── _env.py                      shared .env reader
├── assets/fonts/                    Inter (OFL, licence included): has ₹ and true minus; used by brand_chart
├── assets/amc_logos/                AMC logos (icon / wordmark / badge PNGs + index.json). Third-party
│                                    trademarks: gitignored, never committed. Refresh: scripts/amc_logos.py
├── assets/logos/
│   ├── logo_on_dark.png             white + gold wordmark (dark backgrounds)
│   ├── logo_on_light.png            navy + gold wordmark (light backgrounds)
│   ├── symbol_on_dark.png           "G" symbol only
│   └── symbol_on_light.png
└── posts/
    └── <YYYY-MM-DD>-<slug>/         one folder per post
        ├── facts_*.json             evidence from mf_facts.py (every number traces here)
        ├── post.md                  copy-paste post + Evidence table + Caveats
        ├── chart.json / chart.png   exact chart
        ├── bg_prompt.md / bg_vN.png FLUX background (+ .prompt.txt with seed)
        ├── image.png                final visual (chart composited on the chosen background)
        ├── image_prompt.md          Nano Banana prompt (Route B only)
        └── slides/NN.png + carousel.pdf   (carousels only)
```

Python: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12` (has `google-genai`, `pymongo`, `pandas`, `matplotlib`, `Pillow`).
DB: `MUTUALFUND_DATA` / `MUTUALFUND_NAV` on the `localhost:27018` tunnel (connection string in `.env` as `MF_MONGO_URI`).

## Rule 1: Numbers (these override everything else)

1. Every figure in a post or image comes from a `facts_*.json` produced by `mf_facts.py`
   (or a query that follows the same cleaning rules). No numbers from memory or estimates.
2. Run `mf_facts.py health` for each month used, and act on `CAUTION`.
3. Known traps in the raw collection, all handled inside `mf_facts.py`. Never bypass it by
   querying raw fields for a published number:
   - `percent_to_nav` is mixed-scale (a fraction in some AMC-months, notional values on
     derivatives). Weights = `stock_aum_cr / aum_cr`.
   - Partial AMC loads (927 missing scheme-months, e.g. HDFC Mar-25, Bandhan Oct-25) fake
     "selling". Flows are like-for-like schemes only.
   - No corporate-action adjustment in the raw data. HDFC Bank's 1:1 bonus showed up as
     ₹1.6 lakh Cr of phantom buying. Splits are detected by the per-scheme quantity ratio.
   - ISIN changes on splits (TD Power `…01027 → …01035`). Bridged by issuer code.
   - Scheme renames (the Aug-2026 SEBI re-categorisation renamed ~166 schemes, and many lost
     their `amfiCode`). Bridged by holdings similarity.
   - `instrument_type: Equity` includes REITs, InvITs, preference shares and bonds.
     Stocks = ISIN `^INE.{4}01`.
   - Arbitrage funds are excluded from flows (hedged cash legs).
4. Outliers (≥ 3× the next item, > ₹10,000 Cr for one stock, ≥ 30 new schemes) need a
   real-world explanation (IPO, OFS, index inclusion, merger) before being featured.
5. `post.md` always ends with an Evidence table mapping each number to its source.

## Rule 2: Compliance (SEBI)

No buy, sell or hold calls, targets or return promises. Describe what funds did, not what
readers should do. Mandatory closing line:
`Data: AMC monthly portfolio disclosures (SEBI-mandated), GoalFi analysis. Not investment advice. Mutual fund investments are subject to market risks, read all scheme related documents carefully.`

## Rule 3: Brand

- Colours: navy `#172554` · gold `#d29900` · off-white `#F4F6FA` · slate `#33507D` ·
  green `#16A34A` (buying) · red `#B42318` (selling). These match the approved GoalFi report
  standard. Don't introduce other hues.
- Logo: the real file is stamped by code. The image model never draws it.
  Dark background → `assets/logos/logo_on_dark.png` (white + gold); light → `logo_on_light.png`
  (navy + gold), chosen automatically. Originals: `GOALFI_MAIN/GoalFi_AUG2023_LogoFiles/`.
- Format: 1080×1350 (4:5) for single images; carousels are 4:5 slides stitched to PDF.
- Image models never draw numbers in Route A. FLUX paints a text-free background and
  `brand_chart.py` draws every figure. In Route B (Nano Banana), every rendered number must be checked.
- **FLUX licence:** NVIDIA lists FLUX.1-dev as "ready for non-commercial use" under its API
  Trial Terms (commercial terms via sales@blackforestlabs.ai). Status: **not yet confirmed by
  the user** for company-page use. Update this line once settled.
- Look: institutional research chart pack. No stock photos, people, clip-art or emoji walls.
  Top-N fund/AMC lists use `kind: "ranking"`: real AMC logos on white plates, 3D bars drawn by code.
- AMC logos only identify an AMC next to its own data. Never alter, recolour or crop them
  beyond the configured badge, and never let an image model draw one.
- Footer on every visual names **that slide's actual sources**: AMC portfolio disclosures (SEBI)
  for holdings and AUM, AMFI daily NAVs for returns, NSE for index levels. Always end with `· GoalFi analysis`.
- Font: Inter from `assets/fonts/`. Don't use Apple system fonts (not redistributable, and
  Helvetica Neue's TTC only loads its regular weight in matplotlib).

## Rule 4: Writing

Senior quant research voice, plain English. Hook within the first 210 characters. 1,200–1,900
characters total. Company names, not tickers. ₹ Cr / ₹ lakh Cr with Indian digit grouping.
3–5 hashtags. Full structure is in the skill.

## Don'ts

- Don't post to LinkedIn or any external service. The user publishes manually.
- Don't write to MongoDB from this folder. It is read-only analytics.
- Don't commit `.env` or put any credential (Mongo URI, NVIDIA or Gemini key) in code or docs.
- Don't re-extract AMC data from here. Data fixes belong in `MF Tool/ParallelExtract.py`
  (and HDFC, ICICI, ABSL, Motilal, PPFAS and Quant are never re-extracted without the user's say-so).
