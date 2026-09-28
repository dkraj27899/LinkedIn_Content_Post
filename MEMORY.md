# GoalFi LinkedIn Studio: Running Memory

Read before every post. Update after every post (see skill, Step 8).
Keep it tight: rules and facts, not prose.

---

## Voice & feedback (user's rules; apply to every post)

- 2026-09-28: **Stay strictly inside the segment the user names.** If they say "small-cap
  funds", every chart and ranking is small-cap only: no diversified universe, and no index or
  benchmark bars from another segment (they rejected a Nifty 50 bar beside small caps). When the
  topic is a category, confirm the category itself before picking a universe.
- 2026-09-28: **Post text must read as human-written.** No emojis, no divider lines (━), no arrow
  bullets, no template phrases ("Here's the twist", "What it signals:", "Your turn:"). Write like
  an analyst talking: short paragraphs, a bold lead sentence per point, plain numbers. Bold
  (Unicode) only on the hook and section lead-ins; disclaimer and hashtags plain. 3–4 hashtags.
- 2026-09-28: **Include every fund in the named category** (user: "we have to include" all 36
  small caps). Funds launched mid-period are ranked on since-launch return, clearly flagged.
- 2026-09-28: **Check coverage against the user's own knowledge of the market.** They spotted
  Samco Small Cap missing (a plan-name filter bug). Before handing over, list the full universe
  (count + names) and eyeball it for well-known funds that are absent.

---

## Post log

| Date | Slug | Angle | Data month | Headline number | Format | Hook (first line) |
|---|---|---|---|---|---|---|
| | | | | | | |

---

## Data caveats (check each post against these)

- **Audit 28-Sep-2026.** Raw MFDetails has mixed-scale `percent_to_nav`, partial AMC loads,
  no corporate-action adjustment, ISIN changes on splits, and scheme renames. All are handled
  in `mf_facts.py`. Never publish a raw-query number.
- **Months with large holes** (industry totals are understated; flows are fine because they
  are like-for-like): Mar-2025 (HDFC 30 schemes, LIC 30), Apr-2025 (Bandhan 43, Invesco 25,
  Motilal 42), Jun-2025 (Invesco 25), Aug-2025 (Invesco 29), Oct-2025 (Bandhan 37).
- **Aug-2026:** ~166 schemes renamed (SEBI re-categorisation: "Savings" → "Money Market",
  "Equity Hybrid" → "Aggressive Hybrid", "Floater" → "Floating Interest Rates", Omni FoF →
  Active FoF). 57 schemes / ₹1.84 lakh Cr are genuinely missing vs Jul-2026 (SBI 3, HDFC 4,
  DSP 2, Bandhan 8, ABSL 3 …). Don't quote Aug-2026 industry totals without that caveat.
- **NAV plan names:** some AMCs name the growth plan just "<Scheme> - Direct Plan" (Samco, HDFC
  and Motilal index funds). `mf_facts.returns` treats any plan not marked IDCW / income
  distribution / bonus / unclaimed as growth (fixed 2026-09-28; it had dropped Samco Small Cap).
- Coverage: Zerodha has only 7/20 months, Shriram 9/20. Don't make "all AMCs since Jan-2025"
  claims about them.

---

## Story backlog (verified from mf_facts.py on 28-Sep-2026; re-pull before use)

- **Most-owned stock (Aug-2026):** ICICI Bank ₹3,02,843 Cr across 759 schemes / 50 AMCs
  (5.34% of all MF stock holdings), ahead of HDFC Bank ₹2,84,928 Cr (725 schemes, 5.02%).
- **Banks = one-fifth of MF equity:** 20.31% of MF stock holdings (₹11.52 lakh Cr, 38 banks).
- **Small-cap breadth (Aug-2026, AMFI Jun-2026 list):** Large Cap 60.87% of value in 100
  stocks. Small Cap 16.80% spread over 986 stocks. Mid Cap 21.73% in 147 stocks.
- **Breadth:** 1,286 distinct listed stocks held by MFs in Aug-2026 (1,119 in Jan-2025).
- **Eternal (Zomato):** ₹92,320 Cr held by 573 schemes across 44 AMCs (Aug-2026).
- **The great scheme rename (Aug-2026):** ~166 schemes renamed in one month under the SEBI
  re-categorisation. A good explainer post on why your fund's name changed.
- **Aug-2026 flows (active funds, like-for-like):** net ₹47,558 Cr bought. LIC topped at
  ₹23,196 Cr with 96 new schemes. ⚠️ **Verify the cause (OFS?) before featuring.**
  Biggest net sells: ICICI Bank −₹4,531 Cr, Infosys −₹3,376 Cr, Eternal −₹3,348 Cr.
- **HDFC Bank bonus (Aug-2025):** raw data shows ₹1.6 lakh Cr of "buying" that was really a
  1:1 bonus. A good "why naive MF-flow trackers get it wrong" credibility post.
