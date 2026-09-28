# Post: 2026's best funds aren't its biggest

Format: 3-slide carousel (`carousel.pdf`, slides in `slides/01–03.png`, 2160×2700).
Data as of: returns 31 Dec 2025 → 25 Sep 2026 (AMFI NAV); AUM 31 Aug 2026 (AMC disclosures).

## Copy (paste into LinkedIn)

```
The Nifty 50 is down 11.4% in 2026. The best diversified equity fund is up 32.25%.

And not one of the 10 best diversified funds is among India's 10 biggest funds.

We ranked 295 diversified equity funds (direct growth plans, sectoral and thematic funds excluded) on returns from 31 Dec 2025 to 25 Sep 2026. Then we set them against India's 10 largest schemes by AUM.

What the data shows:

→ Small caps ran the table. 8 of the top 10 performers are small-cap funds. The median small-cap fund is up 14.82%; the median large-cap fund is down 5.72%.

→ The indices agree. Nifty Smallcap 250: +8.84%. Nifty 50: −11.44%.

→ The 10 best performers manage ₹46,723 Cr combined. That is less than a third of Parag Parikh Flexi Cap alone (₹1,47,384 Cr).

→ 6 of the 10 largest funds are negative this year. Only Nippon India Small Cap (+11.23%) is in double digits.

→ 293 of 295 diversified funds beat the Nifty 50 index fund (−10.73%). Yet the median fund is up just 0.62%.

So what? 2026 has been a year of breadth, not heavyweights. The index's fall landed hardest on large-cap-heavy portfolios, including the ETFs that hold some of India's biggest pools of money. Nine months is a short window, though, and leadership between market-caps has flipped before.

Does a year like this change how you think about fund size, or is it noise?

Data: AMFI daily NAVs, AMC monthly portfolio disclosures (SEBI-mandated), NSE index closes; GoalFi analysis. Past performance is not indicative of future returns. Not investment advice. Mutual fund investments are subject to market risks, read all scheme related documents carefully.

#MutualFunds #SmallCap #IndianStockMarket #AMFI #GoalFi
```

## Evidence

| Figure | Value | Source file → field |
|---|---|---|
| Nifty 50 index fund YTD | −10.73% | `facts_returns.json` → `benchmark_ret_pct` (UTI Nifty 50 Index Fund, direct growth, code 120716) |
| "Nifty 50 is down 11.4%" (hook) | −11.44% rounded | `facts_indices.json` → `indices.Nifty 50.price_ret_pct` |
| Best diversified fund | +32.25% | `facts_returns.json` → `rows[0].ret_pct` (Bank of India Small Cap, 145678) |
| Funds ranked | 295 | `facts_returns.json` → `funds_in_universe` |
| Small-cap funds in top 10 | 8 | count of `category == Small Cap Fund` in `rows[0:10]` |
| Median small-cap / large-cap fund | +14.82% / −5.72% | `facts_returns.json` → `by_category[].median` |
| Nifty Smallcap 250 / Nifty 50 (price) | +8.84% / −11.44% | `facts_indices.json` → `indices.*.price_ret_pct` (NSE `ind_close_all` 31-12-2025 & 25-09-2026) |
| Top-10 performers' combined AUM | ₹46,723 Cr | `facts_top_performers_aum.json` → `combined_aum_cr_matched` (46,723.44; all 10 matched) |
| Parag Parikh Flexi Cap AUM | ₹1,47,384 Cr | `facts_aum.json` → `rows[1].aum_cr` (1,47,383.63) |
| "Less than a third" | 46,723 ÷ 1,47,384 = 0.317 | arithmetic |
| Largest funds negative YTD | 6 of 10 | `facts_aum_returns.json` → count of `ytd_ret_pct < 0` |
| Nippon India Small Cap YTD | +11.23% | `facts_aum_returns.json` |
| Funds beating Nifty 50 index fund | 293 of 295 | `facts_returns.json` → `funds_beating_benchmark` |
| Median diversified fund | +0.62% | `facts_returns.json` → `median_ret_pct` |
| "Not one of the 10 best diversified funds is among the 10 biggest" | 0 overlap | top-10 codes in `facts_returns.json` vs schemes in `facts_aum.json`; largest top performer is DSP Small Cap at ₹21,662 Cr vs AUM #10 cut-off ₹82,660 Cr |

Slide numbers are generated straight from these files (`slide*.json` built by script, not retyped).

## Caveats

- **Universe:** diversified equity = SEBI equity categories minus Sectoral/Thematic. With themes included, the #1 fund is Nippon India Taiwan Equity (+101.99%), followed by healthcare and defence funds. That's a different story, so it's not used here.
- **Returns:** point-to-point NAV, direct growth plans only (ICICI's "Cumulative" plans counted as growth). ETFs have one NAV and no direct plan. Not annualised. Category is taken from the Sep-2026 label (post SEBI re-categorisation).
- **Benchmark:** the Nifty 50 index fund return includes dividends, net of costs, which is why it differs from the Nifty 50 price index (−11.44%).
- **AUM:** scheme AUM from the Aug-2026 portfolio disclosures. Health gate: 57 schemes are missing vs Jul-2026, but none is near the top-10 cut-off (largest missing < ₹82,660 Cr). The renamed "SBI Aggressive Hybrid Fund" (formerly SBI Equity Hybrid, code 119609) is included correctly. Checks: one AUM value per scheme, holdings sum to 95–100% of AUM.
- **Outlier check:** Bank of India Small Cap's NAV rose steadily across months with no single-day jump over 3.84%. The Nifty 50 fall was verified directly against NSE closes.

## Visual

- Background: FLUX.1-dev (NVIDIA API), `bg_v2.png`, **seed 4124086406** (prompt in `bg_prompt.md` / `bg_v2.png.prompt.txt`).
- Slides: `brand_chart.py --background bg_v2.png`, scale 2 (2160×2700), Inter font.
- Licence reminder: FLUX.1-dev on the NVIDIA API is listed "for non-commercial use". Confirm terms before posting on the company page.
