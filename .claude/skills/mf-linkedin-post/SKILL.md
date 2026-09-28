---
name: mf-linkedin-post
description: Create a GoalFi LinkedIn post (copy + branded visual via NVIDIA FLUX or Nano Banana) from Indian mutual-fund portfolio data in MUTUALFUND_DATA.MFDetails — what funds bought/sold, top holdings, sector or market-cap mix, a stock's MF ownership, industry data stories. Use whenever the user asks for a LinkedIn post, carousel, social post or infographic about mutual-fund holdings, flows or MF data.
---

# GoalFi LinkedIn post from mutual-fund holdings data

You are writing as GoalFi's **senior quant research lead**. Posts are public, carry the GoalFi
brand and are read by investors, advisors and industry people. A wrong number costs trust
that no hook can win back, so the data rules come first and the writing comes second.

Workspace: `/Users/dikshant/GOALFI_MAIN/GoalFi LinkedIn Studio/`. Run every command from that root (`cd` there first). Python: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`.

## Step 0: Load context (every time)

1. Read `CLAUDE.md`, which covers rules, brand, tools and folder layout.
2. Read `MEMORY.md`. It holds the post log (don't repeat an angle or hook that
   was used recently), the user's voice feedback, and the story backlog.
3. The DB tunnel must be up (`localhost:27018`). If `scripts/mf_facts.py months` fails, tell the user
   to start the tunnel. Do not guess numbers.

## Step 1: Pin the angle

From the user's prompt, decide:
- **Post type:** flows (what funds bought or sold), top holdings, sector mix, market-cap mix,
  stock spotlight, or a data story (e.g. the Aug-2026 SEBI scheme-rename wave).
- **Month(s):** default to the latest month in `mf_facts.py months`.
- **Format:** a single image (4:5) for one idea. A carousel (5–8 slides, PDF) for 3 or more
  ideas or a step-by-step story.

If the prompt is ambiguous on something that changes the numbers (which month, active funds
only or all), ask once. Otherwise pick the sensible default and say which one you picked.

## Step 2: Data-health gate (never skip)

```bash
cd "/Users/dikshant/GOALFI_MAIN/GoalFi LinkedIn Studio"
python3.12 scripts/mf_facts.py health --month YYYY-MM --json posts/<slug>/facts_health.json
```

Run it for **every month the post uses**, and for the previous month too if it's a flows post.
- `renamed` schemes are fine; the tool bridges them automatically.
- `missing_by_amc`: if a large AMC is missing schemes, check that the post's claim doesn't
  depend on it. Flows are computed like-for-like, so a missing scheme is masked, not read as
  selling. But industry **totals** (e.g. "MFs hold ₹X lakh Cr") are understated. Either don't
  quote totals for that month, or say "across N reporting schemes".
- Never use `percent_to_nav` from the raw collection. Use only the numbers from `mf_facts.py`.

## Step 3: Pull the facts, which become the evidence file

```bash
python3.12 scripts/mf_facts.py flows   --month YYYY-MM [--active-only] --n 15 --json posts/<slug>/facts_flows.json
python3.12 scripts/mf_facts.py top     --month YYYY-MM --n 15             --json posts/<slug>/facts_top.json
python3.12 scripts/mf_facts.py sectors --month YYYY-MM                    --json posts/<slug>/facts_sectors.json
python3.12 scripts/mf_facts.py caps    --month YYYY-MM                    --json posts/<slug>/facts_caps.json
python3.12 scripts/mf_facts.py stock   --month YYYY-MM --q "NAME|ISIN"    --json posts/<slug>/facts_stock.json
python3.12 scripts/mf_facts.py returns --start 2025-12-31 [--end YYYY-MM-DD] --universe diversified|equity|all --json posts/<slug>/facts_returns.json
python3.12 scripts/mf_facts.py aum     --month YYYY-MM --n 10             --json posts/<slug>/facts_aum.json
```

For **performance posts**, ask which universe to use if the user hasn't said: diversified
equity (the like-for-like default), all equity (themes dominate), or all funds. Returns use
direct growth plans (ICICI "Cumulative" counts as growth). Verify any headline index move
against NSE's `nsearchives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv`, and save
it as `facts_indices.json`.

If a question needs something these commands can't answer, write a query that follows the
cleaning rules in the `mf_facts.py` docstring, and save its output as a `facts_*.json` too.

**Every number in the post and the image must exist in a `facts_*.json`**, or be a direct
arithmetic result of numbers there (show the arithmetic in `post.md`'s evidence section).

## Step 4: Sanity-check outliers before featuring them

A number is an outlier if it is ≥ 3× the next item, a single stock's net buy is over ₹10,000 Cr,
`new_schemes` is ≥ 30, or it contradicts well-known market facts. Before building a post
around one:
- Look for a cause: IPO or listing, OFS or block deal, index inclusion, merger, split with an
  ISIN change, QIP. Use WebSearch if available.
- Check `ca_adjusted`, `ca_excluded` and `isin_changes_bridged` in the flows JSON.
- **Explained:** feature it and give the reason in one line ("bought in the government's OFS").
- **Unexplained:** don't feature it. Tell the user it looks like a possible data artifact.

## Step 5: Write the post (`posts/<slug>/post.md`)

**Structure** (1,200–1,900 characters in total):
1. **Hook** (the first ~210 characters show before "…see more"). One sharp, specific, numeric
   observation. No "In today's world", no rhetorical "Did you know?".
2. **Context line**: what the data is ("Every AMC discloses its full portfolio monthly. We
   parsed 2,109 schemes across 52 fund houses.").
3. **3–5 insights**: a bold lead sentence, then one or two plain sentences with the numbers.
   No emojis, no arrows or dividers, no template phrases. It must read as human-written (see
   MEMORY.md, Voice & feedback).
4. **So what**: one or two lines interpreting what it signals, as an observation, not advice.
5. **Question to readers** to drive comments.
6. **Method + disclaimer** (short, mandatory; see Compliance).
7. **Hashtags**: 3–5, e.g. `#MutualFunds #IndianStockMarket #AMFI #PortfolioAnalytics #GoalFi`.

**Voice:** institutional-research precise, plain English, confident, no hype. Short sentences.
Write company names, not tickers (ICICIBANK → ICICI Bank, ETERNAL → Eternal (Zomato)).
Use Indian units: ₹ Cr and ₹ lakh Cr, with Indian digit grouping (₹1,23,456 Cr). Round sensibly
in prose (₹23,196 Cr → "₹23,196 Cr" or "~₹23,200 Cr") but never change a number's meaning.
Apply the voice feedback recorded in MEMORY.md.

**Compliance (SEBI; non-negotiable):**
- No buy, sell or hold calls, price targets, "multibagger", "next big stock", or return promises.
- Describe what funds did. Never tell the reader what to do.
- Don't single out a named fund manager negatively.
- End with: `Data: AMC monthly portfolio disclosures (SEBI-mandated), GoalFi analysis. Not investment advice. Mutual fund investments are subject to market risks, read all scheme related documents carefully.`
- Say the data is as of the month-end disclosed, e.g. "as of 31 Aug 2026".

`post.md` layout: the copy-paste post inside one fenced block, then an **Evidence** table
(every number → which facts file and field), then **Caveats** (health-gate notes, outlier
explanations).

## Step 6: The visual

Pick the route by which key is in `.env`. **Route A (NVIDIA FLUX) is the default.**
Either way, numbers are never left to an image model to draw.

1. **Chart first, always.** Build the slide JSON *by script from the facts files* (never retype
   numbers). `brand_chart.py` supports `"kind": "bars"` (signed or brand colours, a `tag` column
   such as YTD return, a benchmark bar via per-bar `color` + `separator_before`) and
   `"kind": "cover"` (headline + stat tiles + swipe cue), and **`"kind": "ranking"`, the
   default for any top-N list of funds or AMCs**: rank · AMC logo plate · 3D crystal bar ·
   exact value · right-hand metric, with `highlight` for a row to call out. Logos come from
   `scripts/amc_logos.py` (the same AMFI assets the GoalFi Tracking portal uses). Resolve them
   with `amc_logos.logo_for(fund_house)` and assert that every row has one before rendering.
   Use `bar_len` to leave room when value labels are wide. It renders at 2× (2160×2700) by
   default. Set each slide's `footer` to its **real** sources: NAV-based returns are
   "AMFI daily NAVs", not portfolio disclosures. Then run
   `python3.12 scripts/brand_chart.py --data posts/<slug>/chart.json --out posts/<slug>/chart.png`.
   This is the exact version and the fallback final image.

**Route A: FLUX background + exact chart** (needs `NVIDIA_API_KEY`)

2. Write `posts/<slug>/bg_prompt.md`: one or two sentences describing a scene that fits the
   story, with no text in it. For example, rising gold light trails for buying, a cooling
   downward flow for selling, a dense constellation for breadth. The script adds the brand and
   no-text rules itself. Keep the top quarter and centre calm.
3. Generate 2–3 backgrounds and pick the one with the calmest centre:
   `python3.12 scripts/flux_nvidia.py --prompt-file posts/<slug>/bg_prompt.md --n 3 --out posts/<slug>/bg.png`
4. Composite:
   `python3.12 scripts/brand_chart.py --data posts/<slug>/chart.json --background posts/<slug>/bg_vN.png --out posts/<slug>/image.png`
5. Read `image.png` and check: the headline is readable over the art, there's no stray text
   or glyphs in the background, and the art isn't too busy behind the card. If the background
   is bad, regenerate it; the numbers never need fixing, because code draws them.
6. The seed is saved in `bg*.png.prompt.txt`. Record the chosen seed in `post.md`, so the
   image can be reproduced with `--seed`.
7. **Licence:** FLUX.1-dev on the NVIDIA API is listed "for non-commercial use" under the
   NVIDIA Trial Terms. Remind the user once per post, until they confirm commercial terms are
   settled (then record that in MEMORY.md and stop reminding).

**Route B: Nano Banana** (needs `GEMINI_API_KEY`; renders the text itself)

2. Write `posts/<slug>/image_prompt.md` with the headline, subline, exact labels and numbers
   (copied from `chart.json`), the layout, and the logo corner (top-right). About 40 words of
   on-image text at most.
3. `python3.12 scripts/nano_banana.py --prompt-file posts/<slug>/image_prompt.md --ref posts/<slug>/chart.png --n 2 --out posts/<slug>/image.png`
4. **Read every PNG** and check each number, ₹ sign, comma, spelling, and that there's no fake
   logo. Fix with `--edit posts/<slug>/image_v1.raw.png --prompt "Change X to Y, keep everything else"`,
   at most 2 edits. If it's still wrong, use Route A or `chart.png`.

**Carousels** (either route): make one image per slide as `slides/01.png` …, then
`python3.12 scripts/nano_banana.py --pdf "posts/<slug>/slides/*.png" --out posts/<slug>/carousel.pdf`
(PDF stitching needs no API key).

**No image key at all:** `chart.png` is the visual; tell the user how to add a key (`.env.example`).

## Step 7: Hand over

Show the user the post in one copy-paste fenced block, the image path(s) (and carousel PDF),
and a 2–3 line caveat summary. Do **not** post to LinkedIn yourself; the user publishes.
Offer 2 alternative hooks in case they want a different opening.

## Step 8: Record it

When the user approves (or says it's posted), append a row to the **Post log** in
`MEMORY.md`: date, slug, angle, month of data, headline number, format, and
the hook's first line. Any feedback on voice, design or length goes under **Voice & feedback**
as a rule, so the next post starts from it. Move backlog ideas that were used out of the backlog.
