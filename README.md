# GoalFi LinkedIn Studio

Turns India's monthly mutual-fund portfolio disclosures into data-backed LinkedIn posts,
with verified numbers, SEBI-safe copy and GoalFi-branded visuals (FLUX.1-dev via the NVIDIA API, or Google's Nano Banana).

Every month, each Indian AMC discloses its full scheme portfolios. GoalFi's extraction
pipeline loads them into MongoDB (about 2.2 million holdings across 52 fund houses, from
January 2025 onward). This project reads that data and produces ready-to-publish posts on
what funds bought and sold, the most-owned stocks, sector and market-cap mix, and single-stock
ownership. Every figure traces back to a saved evidence file.

```
MongoDB (MFDetails)  →  mf_facts.py  →  facts_*.json  →  post.md  +  FLUX background + exact chart
      raw holdings        cleaned        evidence         copy         branded 1080×1350 visual
```

## Why a cleaning layer

Raw AMC disclosures can't be used as-is. A data audit of the holdings collection found
issues that would put wrong numbers into a public post. `scripts/mf_facts.py` corrects
for all of them:

| Problem in the raw data | Effect if ignored | How it's handled |
|---|---|---|
| `% to NAV` reported on different scales | Wrong portfolio weights | Weight = holding value ÷ scheme AUM |
| Some months are missing part of an AMC's schemes | Fake ₹1 lakh Cr+ "selling" months | Flows compare only schemes present in both months |
| Stock splits and bonuses not adjusted | HDFC Bank's 1:1 bonus showed ₹1.6 lakh Cr of fake buying | Detected from the quantity ratio of funds that didn't trade the stock |
| New ISIN issued after a split | Looks like every fund exited and re-entered the stock | Old and new ISIN linked by issuer code |
| Schemes renamed (~166 in the Aug-2026 SEBI recategorisation) | Renamed schemes look closed or new | Linked by how closely their holdings match |
| "Equity" field includes REITs, InvITs and bonds | Stock counts and totals inflated | Only listed stocks are counted (ISIN pattern `INE….01…`) |
| Arbitrage funds' hedged positions | Hedged trades counted as directional buying | Excluded from flows |

A `health` command checks each month's completeness before anything is published.

## Project structure

```
GoalFi LinkedIn Studio/
├── README.md
├── CLAUDE.md                          rules for the AI assistant: numbers, compliance, brand, writing
├── MEMORY.md                          post log, style feedback, data caveats, story backlog
├── .env.example                       template for local secrets (.env is gitignored)
├── .claude/skills/mf-linkedin-post/
│   └── SKILL.md                       step-by-step workflow for Claude Code
├── scripts/
│   ├── mf_facts.py                    cleaned facts from MongoDB (the only source of numbers)
│   ├── flux_nvidia.py                 FLUX.1-dev (NVIDIA API) text-free background art
│   ├── brand_chart.py                 exact-number branded chart, composited onto the background
│   ├── amc_logos.py                   caches AMC logos from the AMFI directory (as used in GoalFi Tracking)
│   ├── nano_banana.py                 optional Gemini (Nano Banana) route and carousel PDFs
│   └── _env.py                        shared .env reader
├── assets/fonts/                      Inter typeface (SIL Open Font License)
├── assets/amc_logos/                  AMC logos, fetched locally (not committed: third-party trademarks)
├── assets/logos/                      GoalFi wordmark and symbol, dark and light versions
└── posts/<YYYY-MM-DD>-<slug>/         one folder per post: evidence, copy, images
```

## Setup

Requirements: Python 3.12, access to the GoalFi MongoDB (`MUTUALFUND_DATA`, `MUTUALFUND_NAV`;
read-only access is enough), and an NVIDIA API key (build.nvidia.com) for images. A Google
Gemini key is optional.

```bash
pip install pymongo pandas numpy matplotlib pillow requests google-genai cairosvg
python3.12 scripts/amc_logos.py       # one-time: fetch AMC logos (needs Homebrew cairo on macOS)
cp .env.example .env        # then fill in MF_MONGO_URI and NVIDIA_API_KEY
```

Run all commands from the project root.

## Usage

**1. Check the data, then pull the facts**

```bash
python3.12 scripts/mf_facts.py months                                   # months available
python3.12 scripts/mf_facts.py health  --month 2026-08                  # completeness check
python3.12 scripts/mf_facts.py flows   --month 2026-08 --active-only --json posts/<slug>/facts_flows.json
python3.12 scripts/mf_facts.py top     --month 2026-08 --n 15           # most-owned stocks
python3.12 scripts/mf_facts.py sectors --month 2026-08                  # industry mix
python3.12 scripts/mf_facts.py caps    --month 2026-08                  # Large / Mid / Small cap mix
python3.12 scripts/mf_facts.py stock   --month 2026-08 --q "ICICI"      # one stock's MF owners
python3.12 scripts/mf_facts.py returns --start 2025-12-31 --universe diversified   # YTD fund returns (AMFI NAV)
python3.12 scripts/mf_facts.py aum     --month 2026-08 --n 10           # largest schemes by AUM
```

**2. Make the visual (default: FLUX background + exact chart)**

```bash
# Text-free background art from FLUX.1-dev: 3 variants, each saved with its seed
python3.12 scripts/flux_nvidia.py --prompt-file posts/<slug>/bg_prompt.md --n 3 --out posts/<slug>/bg.png

# Draw the exact chart, headline and logo on the chosen background
python3.12 scripts/brand_chart.py --data posts/<slug>/chart.json \
    --background posts/<slug>/bg_v2.png --out posts/<slug>/image.png

# Chart on a plain background (fallback)
python3.12 scripts/brand_chart.py --data posts/<slug>/chart.json --out posts/<slug>/chart.png
```

FLUX draws no text or numbers; every figure is drawn by code, so it can't be wrong.

**Optional: Nano Banana (Gemini) renders the whole image, including text**

```bash
# 2 variants, with the exact chart as a layout reference
python3.12 scripts/nano_banana.py --prompt-file posts/<slug>/image_prompt.md \
    --ref posts/<slug>/chart.png --n 2 --out posts/<slug>/image.png

# Fix a detail without regenerating everything
python3.12 scripts/nano_banana.py --edit posts/<slug>/image_v1.raw.png \
    --prompt "Change 4,530 to 4,531; keep everything else" --out posts/<slug>/image_v2.png

# Carousel (any route, no API key needed): stitch slide images into the PDF LinkedIn accepts
python3.12 scripts/nano_banana.py --pdf "posts/<slug>/slides/*.png" --out posts/<slug>/carousel.pdf
```

The real GoalFi logo is added to each image in code; image models never draw it. Every
generated image is saved with its exact prompt (`.prompt.txt`, plus the seed for FLUX), so
any published visual can be reproduced.

> **Licence note:** NVIDIA lists FLUX.1-dev as ready for non-commercial use under its API Trial
> Terms; commercial terms are available from Black Forest Labs. Confirm your terms before
> publishing on a company page.

**3. With Claude Code**

The `mf-linkedin-post` skill runs the full workflow: health check → facts → outlier check →
copy → visual → number check → hand-over → log. Ask for a post in plain language, e.g.
*"Make a LinkedIn post on what active funds bought in August 2026."*

## Content rules

- **Every number traces to evidence.** Each post's `post.md` ends with a table mapping every
  figure to its `facts_*.json` source.
- **Unusual numbers get checked.** A large figure, such as heavy buying of one stock, is only
  featured once its real-world cause (IPO, share sale, index inclusion) is confirmed.
- **SEBI-compliant.** No buy/sell calls, price targets or return promises. Posts describe what
  funds did, never what readers should do. Every post carries the mutual-fund risk disclaimer.
- **Brand.** Navy `#172554` and gold `#d29900`, 1080×1350 portrait, institutional
  chart-pack style.
- Posts are published manually. Nothing in this project posts to LinkedIn or writes to the
  database.

## Data source

AMC monthly portfolio disclosures (SEBI-mandated), extracted by GoalFi's MF Tool pipeline.
Market-cap buckets use AMFI's half-yearly Large/Mid/Small Cap lists; scheme categories use
AMFI scheme master data.

---

*Not investment advice. Mutual fund investments are subject to market risks, read all scheme
related documents carefully.*
