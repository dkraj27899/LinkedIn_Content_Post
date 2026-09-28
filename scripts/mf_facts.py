"""
mf_facts.py — audit-safe facts from MUTUALFUND_DATA.MFDetails for public LinkedIn posts.
(Run every command from the GoalFi LinkedIn Studio root folder.)

Every number that goes into a post must come from this file (or be verified against it).
It bakes in the cleaning rules from the 28-Sep-2026 data audit, so the raw collection's
known traps cannot leak into something we publish:

  1. Weights  = stock_aum_cr / aum_cr            (percent_to_nav is mixed-scale — never used)
  2. Month key = year-month of `date`            (UTI once stored month-end dates)
  3. Stocks    = Equity rows with ISIN ^INE....01 (drops REITs, InvITs, prefs, bonds, INF, IN9)
  4. Flows     = like-for-like schemes only       (a scheme missing in either month is masked,
                                                  so partial AMC loads can't fake "selling")
  5. Flows     = arbitrage funds excluded         (hedged cash legs aren't directional buying)
  6. Flows     = corporate actions neutralised    (price ratio snapped to split/bonus factor,
                                                  unsnappable jumps excluded and reported)
  7. Prices    = median implied price per ISIN-month (a few AMCs report qty 10x off)
  8. Renames   = schemes renamed month-to-month are bridged by holdings similarity
                 (Aug-2026 SEBI re-categorisation renamed ~166 schemes; many lost amfiCode)
  9. ISINs     = a stock whose ISIN changed (split -> new ISIN) is bridged to its new ISIN

Usage:
  python3.12 scripts/mf_facts.py months
  python3.12 scripts/mf_facts.py health  --month 2026-08
  python3.12 scripts/mf_facts.py top     --month 2026-08 --n 15
  python3.12 scripts/mf_facts.py flows   --month 2026-08 [--prev 2026-07] [--n 15] [--active-only]
  python3.12 scripts/mf_facts.py sectors --month 2026-08 [--n 15]
  python3.12 scripts/mf_facts.py caps    --month 2026-08
  python3.12 scripts/mf_facts.py stock   --month 2026-08 --q "ETERNAL"      (name or ISIN)
  python3.12 scripts/mf_facts.py returns --start 2025-12-31 [--end 2026-09-25] [--universe diversified|equity|all] [--plan direct]
  python3.12 scripts/mf_facts.py aum     --month 2026-08 --n 10            (largest schemes by AUM)
  add --json posts/<slug>/facts_<cmd>.json to any command to save the evidence.
"""
import argparse
import json
import os
import re
import sys
from functools import lru_cache

import numpy as np
import pandas as pd
from pymongo import MongoClient

import _env

MONGO_URI = _env.get("MF_MONGO_URI")
STOCK_ISIN = "^INE.{4}01"
PASSIVE_RE = re.compile(r"\b(?:ETF|Index|Indx)\b|Exchange Traded|\bNifty\b|\bBSE\b|\bSensex\b", re.I)
ARB_RE = re.compile(r"Arbitrage", re.I)
# Split / bonus factors a price ratio can snap to (1:1 bonus = 2, FV 10->2 = 5, ...)
CA_FACTORS = [1.5, 2, 2.5, 3, 4, 5, 10, 20]


def _client():
    if not MONGO_URI:
        raise SystemExit("MF_MONGO_URI not set. Add it to .env (see .env.example).")
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)


def _period(s):
    return pd.Period(s, "M")


def _bounds(m):
    p = _period(m)
    return p.start_time.to_pydatetime(), (p + 1).start_time.to_pydatetime()


@lru_cache(maxsize=None)
def scheme_categories():
    """amfiCode -> AMFI scheme category (e.g. 'Equity Scheme - Small Cap Fund')."""
    sd = _client().MUTUALFUND_NAV.Scheme_Data
    return {str(d["Code"]): d.get("Scheme Category") for d in sd.find({}, {"Code": 1, "Scheme Category": 1})}


@lru_cache(maxsize=None)
def months():
    col = _client().MUTUALFUND_DATA.MFDetails
    ds = col.distinct("date")
    return sorted({pd.Timestamp(d).to_period("M") for d in ds})


@lru_cache(maxsize=None)
def equity(m):
    """Clean stock-level holdings for one month (one row per scheme x stock)."""
    lo, hi = _bounds(m)
    col = _client().MUTUALFUND_DATA.MFDetails
    cur = col.find(
        {"date": {"$gte": lo, "$lt": hi}, "instrument_type": "Equity", "isin": {"$regex": STOCK_ISIN}},
        {"_id": 0, "isin": 1, "name": 1, "fundHouse": 1, "schemeName": 1, "amfiCode": 1,
         "quantity": 1, "stock_aum_cr": 1, "aum_cr": 1, "industry": 1, "sector": 1},
    )
    df = pd.DataFrame(list(cur))
    if df.empty:
        raise SystemExit(f"No equity rows for {m}")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["weight"] = df["stock_aum_cr"] / df["aum_cr"].where(df["aum_cr"] > 0)
    cats = scheme_categories()
    df["category"] = df["amfiCode"].astype(str).map(cats)
    df["arbitrage"] = df["schemeName"].str.contains(ARB_RE) | df["category"].fillna("").str.contains(ARB_RE)
    df["passive"] = df["schemeName"].str.contains(PASSIVE_RE)
    df["industry"] = df["industry"].fillna(df["sector"])
    # Median implied price per ISIN; rows >5x away from it have unit errors in quantity
    ok = (df.quantity > 0) & (df.stock_aum_cr > 0)
    df.loc[ok, "px"] = df.loc[ok, "stock_aum_cr"] * 1e7 / df.loc[ok, "quantity"]
    df["px_med"] = df.groupby("isin")["px"].transform("median")
    dev = df["px"] / df["px_med"]
    df["qty_suspect"] = (dev > 5) | (dev < 0.2)
    # Canonical display name = most common name for the ISIN this month
    df["stock"] = df.groupby("isin")["name"].transform(lambda s: s.mode().iat[0] if not s.mode().empty else s.iat[0])
    return df


@lru_cache(maxsize=None)
def scheme_presence():
    """(fundHouse, schemeName) x month presence matrix with AUM — used for hole detection."""
    col = _client().MUTUALFUND_DATA.MFDetails
    rows = col.aggregate([
        {"$group": {"_id": {"f": "$fundHouse", "s": "$schemeName",
                            "m": {"$dateToString": {"format": "%Y-%m", "date": "$date"}}},
                    "aum": {"$max": "$aum_cr"}}}
    ], allowDiskUse=True)
    df = pd.DataFrame([{**r["_id"], "aum": r["aum"]} for r in rows])
    return df.pivot_table(index=["f", "s"], columns="m", values="aum", aggfunc="max")


@lru_cache(maxsize=None)
def _holding_vectors(m):
    """Every scheme's holdings for a month as (fundHouse, schemeName, isin, value) — all asset types."""
    lo, hi = _bounds(m)
    col = _client().MUTUALFUND_DATA.MFDetails
    rows = col.aggregate([
        {"$match": {"date": {"$gte": lo, "$lt": hi}}},
        {"$group": {"_id": {"f": "$fundHouse", "s": "$schemeName", "i": "$isin"}, "v": {"$sum": "$stock_aum_cr"}}},
    ], allowDiskUse=True)
    df = pd.DataFrame([{**r["_id"], "v": abs(r["v"] or 0)} for r in rows])
    # Cash/TREPS (PHYS*) is shared by everything — a matured fund holding only TREPS would
    # otherwise "match" any scheme that also holds TREPS.
    df = df[~df["i"].fillna("").str.startswith("PHYS")]
    return {k: g.set_index("i")["v"] for k, g in df.groupby(["f", "s"])}


@lru_cache(maxsize=None)
def match_renames(prev, m, min_sim=0.8):
    """
    Schemes that vanished between `prev` and `m` paired with schemes that appeared in `m`,
    same AMC, when their holdings are near-identical (cosine similarity on ISIN values).
    Needed because AMCs rename schemes (SEBI re-categorisation, 'Flexicap' -> 'Flexi Cap')
    and the renamed rows often lose their amfiCode, breaking month-on-month identity.
    """
    a, b = _holding_vectors(str(_period(prev))), _holding_vectors(str(_period(m)))
    gone, new = set(a) - set(b), set(b) - set(a)
    pairs = []
    for f in {k[0] for k in gone} & {k[0] for k in new}:
        for ko in (k for k in gone if k[0] == f):
            for kn in (k for k in new if k[0] == f):
                x, y = a[ko], b[kn]
                shared = len(x.index.intersection(y.index))
                size = x.sum() / y.sum() if y.sum() else 0
                if shared < min(3, len(x), len(y)) or not 0.5 <= size <= 2:
                    continue
                idx = x.index.union(y.index)
                xx, yy = x.reindex(idx, fill_value=0), y.reindex(idx, fill_value=0)
                den = np.sqrt((xx ** 2).sum() * (yy ** 2).sum())
                if den:
                    pairs.append((float((xx * yy).sum() / den), ko, kn))
    used, out = set(), []
    for sim, ko, kn in sorted(pairs, reverse=True):
        if sim >= min_sim and ko not in used and kn not in used:
            used |= {ko, kn}
            out.append({"amc": ko[0], "old_name": ko[1], "new_name": kn[1], "similarity": round(sim, 3)})
    return tuple(tuple(d.items()) for d in out)


def renames(prev, m):
    return [dict(t) for t in match_renames(str(_period(prev)), str(_period(m)))]


def health(m):
    """Data-health gate for a month: schemes missing vs the months around it (renames excluded)."""
    p = scheme_presence()
    ms = list(p.columns)
    m = str(_period(m))
    if m not in ms:
        raise SystemExit(f"{m} not in data")
    i = ms.index(m)
    latest = i + 1 == len(ms)
    if i == 0:
        missing = pd.Series(False, index=p.index)
    else:
        # Reported last month, absent now. For past months also require it to reappear later
        # (a true hole); for the latest month we can't know yet — closure/merger or partial load.
        missing = p[m].isna() & p[ms[i - 1]].notna()
        if not latest:
            missing &= p[ms[i + 1:]].notna().any(axis=1)
    ren = renames(ms[i - 1], m) if i else []
    renamed = {(r["amc"], r["old_name"]) for r in ren}
    missing &= ~p.index.isin(list(renamed))
    miss = p[missing].copy()
    miss["aum_prev"] = p.loc[missing, ms[i - 1]] if i else np.nan
    by_amc = (miss.reset_index().groupby("f").agg(schemes=("s", "size"), aum_cr=("aum_prev", "sum"))
              .sort_values("aum_cr", ascending=False))
    total_aum = p[m].sum()
    return {
        "month": m,
        "schemes_reported": int(p[m].notna().sum()),
        "amcs_reported": int(p[m].notna().groupby(level=0).any().sum()),
        "aum_reported_cr": round(float(total_aum), 0),
        "renamed_schemes": len(ren),
        "renamed": ren,
        "missing_schemes": int(len(miss)),
        "missing_aum_cr": round(float(miss["aum_prev"].sum()), 0),
        "missing_by_amc": by_amc.round(0).reset_index().rename(columns={"f": "amc"}).to_dict("records"),
        "is_latest_month": latest,
        "verdict": "OK" if miss["aum_prev"].sum() < 0.01 * total_aum else "CAUTION — check missing_by_amc before publishing",
    }


def top_holdings(m, n=15):
    df = equity(m)
    g = df.groupby(["isin", "stock"]).agg(mf_value_cr=("stock_aum_cr", "sum"), schemes=("schemeName", "nunique"),
                                         amcs=("fundHouse", "nunique"), industry=("industry", "first"))
    g = g.sort_values("mf_value_cr", ascending=False).reset_index()
    total = df["stock_aum_cr"].sum()
    g["share_of_mf_equity_pct"] = g["mf_value_cr"] / total * 100
    return g.head(n), {"month": m, "mf_stock_holdings_cr": round(total, 0), "distinct_stocks": int(df["isin"].nunique())}


def _stock_month(df):
    d = df[~df.qty_suspect & (df.quantity > 0)]
    return d.groupby("isin").agg(stock=("stock", "first"), q=("quantity", "sum"), px=("px_med", "first"),
                                 mv=("stock_aum_cr", "sum"), industry=("industry", "first"))


def flows(m, prev=None, n=15, active_only=False):
    """Net buying/selling per stock between two months, like-for-like schemes, CA-neutralised."""
    prev = prev or str(_period(m) - 1)
    a, b = equity(prev), equity(m)
    keep = lambda d: d[~d.arbitrage & (~d.passive if active_only else True)]
    a, b = keep(a), keep(b)
    # Carry renamed schemes across the month boundary under their old name
    rmap = {(r["amc"], r["new_name"]): r["old_name"] for r in renames(prev, m)}
    b = b.assign(schemeName=[rmap.get((f, s), s) for f, s in zip(b.fundHouse, b.schemeName)])
    # Splits often mint a new ISIN for the same issuer (TD Power INE419M01027 -> ...01035).
    # Re-key an ISIN that vanished to the single new ISIN of the same issuer (chars 3-6).
    ia, ib = set(a["isin"]), set(b["isin"])
    gone, fresh = ia - ib, ib - ia
    by_issuer = {}
    for i in fresh:
        by_issuer.setdefault(i[3:7], []).append(i)
    isin_map = {i: by_issuer[i[3:7]][0] for i in gone if len(by_issuer.get(i[3:7], [])) == 1}
    a = a.assign(isin=a["isin"].replace(isin_map))
    both = set(zip(a.fundHouse, a.schemeName)) & set(zip(b.fundHouse, b.schemeName))
    inb = lambda d: d[[k in both for k in zip(d.fundHouse, d.schemeName)]]
    a, b = inb(a), inb(b)
    x, y = _stock_month(a), _stock_month(b)
    j = x.join(y, how="outer", lsuffix="0", rsuffix="1")
    j["stock"] = j["stock1"].fillna(j["stock0"])
    j["industry"] = j["industry1"].fillna(j["industry0"])
    j[["q0", "q1", "mv0", "mv1"]] = j[["q0", "q1", "mv0", "mv1"]].fillna(0)
    # Per-scheme quantities — drive split detection and buy/sell breadth
    clean_rows = lambda d: d[~d.qty_suspect & (d.quantity > 0)]
    sa = clean_rows(a).groupby(["isin", "fundHouse", "schemeName"])["quantity"].sum()
    sb = clean_rows(b).groupby(["isin", "fundHouse", "schemeName"])["quantity"].sum()
    s = pd.concat([sa.rename("q0"), sb.rename("q1")], axis=1).fillna(0).reset_index()
    # Split/bonus detection: funds that didn't trade show quantity x factor exactly, so the
    # median per-scheme quantity ratio snaps to the factor. Price alone is ambiguous (TD Power
    # Aug-26: 1:1 split + 37% rally = price ratio 0.69, inside any "no-split" band).
    held = s[(s.q0 > 0) & (s.q1 > 0)].assign(qr=lambda d: d.q1 / d.q0)
    qratio = held.groupby("isin")["qr"].median()
    by_isin = dict(tuple(held.groupby("isin")["qr"]))

    def exact_hits(isin, k):
        """How many funds sit exactly on factor k (±0.5%) — the fingerprint of a real split."""
        v = by_isin.get(isin)
        return 0 if v is None else int((np.abs(np.log(v / k)) <= 0.005).sum())
    ratio = j["px1"] / j["px0"]
    factors = CA_FACTORS + [1 / f for f in CA_FACTORS]
    j["ca_factor"] = 1.0
    j["ca_note"] = ""
    for isin in j.index:
        r, qr = ratio.get(isin), qratio.get(isin)
        k = None
        if pd.notna(qr) and abs(np.log(qr)) > 0.03:
            snap = min(factors, key=lambda f: abs(np.log(qr / f)))
            if (abs(np.log(qr / snap)) <= 0.03 and exact_hits(isin, snap) >= 2
                    and (pd.isna(r) or 0.5 <= r * snap <= 1.6)):
                k = snap
        if k:
            j.at[isin, "ca_factor"] = k
            j.at[isin, "ca_note"] = f"split/bonus x{k:g} adjusted" if k > 1 else f"consolidation /{1 / k:g} adjusted"
        elif pd.notna(r) and not 0.6 <= r <= 1.6:
            j.at[isin, "ca_note"] = f"EXCLUDED: price ratio {r:.2f} with no clean split signal"
    px = j["px1"].fillna(j["px0"])
    j["net_buy_cr"] = (j["q1"] - j["q0"] * j["ca_factor"]) * px / 1e7
    s["k"] = s["isin"].map(j["ca_factor"]).fillna(1)
    s["dq"] = s["q1"] - s["q0"] * s["k"]
    breadth = s.groupby("isin").agg(schemes_added=("dq", lambda v: int((v > 0).sum())),
                                    schemes_cut=("dq", lambda v: int((v < 0).sum())))
    breadth["new_schemes"] = s[(s.q0 == 0) & (s.q1 > 0)].groupby("isin").size()
    breadth["full_exits"] = s[(s.q0 > 0) & (s.q1 == 0)].groupby("isin").size()
    j = j.join(breadth).fillna({"new_schemes": 0, "full_exits": 0})
    clean = j[~j["ca_note"].str.startswith("EXCLUDED")]
    cols = ["stock", "industry", "net_buy_cr", "mv1", "schemes_added", "schemes_cut", "new_schemes", "full_exits", "ca_note"]
    buys = clean.sort_values("net_buy_cr", ascending=False)[cols].head(n).reset_index()
    sells = clean.sort_values("net_buy_cr")[cols].head(n).reset_index()
    meta = {
        "month": m, "prev": prev, "active_only": active_only,
        "like_for_like_schemes": len(both),
        "renamed_schemes_bridged": len(rmap),
        "isin_changes_bridged": [f"{o} -> {n}" for o, n in isin_map.items()],
        "total_net_buy_cr": round(float(clean["net_buy_cr"].sum()), 0),
        "gross_buy_cr": round(float(clean.loc[clean.net_buy_cr > 0, "net_buy_cr"].sum()), 0),
        "gross_sell_cr": round(float(clean.loc[clean.net_buy_cr < 0, "net_buy_cr"].sum()), 0),
        "stocks_net_bought": int((clean.net_buy_cr > 0).sum()),
        "stocks_net_sold": int((clean.net_buy_cr < 0).sum()),
        "ca_adjusted": j.loc[j.ca_note.str.contains("adjusted"), ["stock", "ca_note"]].reset_index().to_dict("records"),
        "ca_excluded": j.loc[j.ca_note.str.startswith("EXCLUDED"), ["stock", "ca_note"]].reset_index().to_dict("records"),
        "method": "like-for-like schemes, arbitrage excluded, qty change x current median price, corporate actions neutralised",
    }
    return buys, sells, meta


def sectors(m, n=15):
    df = equity(m)
    g = df.groupby("industry").agg(mf_value_cr=("stock_aum_cr", "sum"), stocks=("isin", "nunique"))
    g["share_pct"] = g["mf_value_cr"] / g["mf_value_cr"].sum() * 100
    return g.sort_values("mf_value_cr", ascending=False).head(n).reset_index(), {"month": m}


def caps(m):
    """Large/Mid/Small split using the AMFI list in force for that month."""
    df = equity(m)
    lo, _ = _bounds(m)
    mc = _client().MUTUALFUND_DATA.MarketCapCategorization
    periods = sorted(p for p in mc.distinct("period_end") if p < lo)
    if not periods:
        raise SystemExit("No AMFI cap list before this month")
    pe = periods[-1]
    cat = {d["isin"]: d["category"] for d in mc.find({"period_end": pe}, {"isin": 1, "category": 1})}
    df = df.assign(cap=df["isin"].map(cat).fillna("Unclassified"))
    g = df.groupby("cap").agg(mf_value_cr=("stock_aum_cr", "sum"), stocks=("isin", "nunique"))
    g["share_pct"] = g["mf_value_cr"] / g["mf_value_cr"].sum() * 100
    return g.sort_values("mf_value_cr", ascending=False).reset_index(), {"month": m, "amfi_list": str(pe.date())}


def stock(m, q):
    df = equity(m)
    hit = df[(df["isin"] == q.upper()) | df["stock"].str.contains(q, case=False, regex=False)]
    if hit.empty:
        raise SystemExit(f"No holdings matching {q!r} in {m}")
    isin = hit.groupby("isin")["stock_aum_cr"].sum().idxmax()
    h = df[df["isin"] == isin]
    by_amc = h.groupby("fundHouse").agg(value_cr=("stock_aum_cr", "sum"), schemes=("schemeName", "nunique")) \
              .sort_values("value_cr", ascending=False).reset_index()
    top_w = h.sort_values("weight", ascending=False)[["fundHouse", "schemeName", "category", "weight", "stock_aum_cr"]].head(10)
    top_w["weight"] = top_w["weight"] * 100
    meta = {"month": m, "isin": isin, "stock": h["stock"].iat[0], "industry": h["industry"].iat[0],
            "mf_value_cr": round(float(h.stock_aum_cr.sum()), 1), "schemes": int(h.schemeName.nunique()),
            "amcs": int(h.fundHouse.nunique()), "top_holders_by_weight": top_w.round(2).to_dict("records")}
    return by_amc, meta


GROWTH_RE = re.compile(r"growth|cumulative", re.I)          # ICICI's older plans say "Cumulative"
# A plan is a growth plan unless its name marks it as a payout option. Don't require the word
# "Growth": some AMCs name the growth plan just "<Scheme> - Direct Plan" (Samco Small Cap,
# HDFC / Motilal index funds), and requiring it silently dropped them.
NOT_GROWTH_RE = re.compile(r"idcw|icdw|idwc|dividend|bonus|segregated|payout|reinvest|"
                           r"income (?:cum )?distribution|unclaimed", re.I)
# Frequency words mark payout plans only when "Growth" is absent ("Monthly Income Plan - Growth" is growth)
PAYOUT_FREQ_RE = re.compile(r"p ?f option|half yearly|quarterly|monthly|weekly|daily", re.I)
UNIVERSES = {
    # SEBI equity categories minus sectoral/thematic = like-for-like diversified funds
    "diversified": lambda c: c.str.contains(r"^Equity Scheme", regex=True) & ~c.str.contains("Sectoral|Thematic"),
    "equity": lambda c: c.str.contains(r"^Equity Scheme", regex=True),
    "all": lambda c: c.notna(),
}
DEFAULT_BENCH = "120716"   # UTI Nifty 50 Index Fund - Direct - Growth (Nifty 50 TRI proxy, net of costs)


def _nav_asof(day, lookback_days=7):
    """Last NAV on/before `day` (within lookback) for every plan code."""
    nav = _client().MUTUALFUND_NAV.NAV_Merged_Data
    hi = pd.Timestamp(day).to_pydatetime()
    lo = (pd.Timestamp(day) - pd.Timedelta(days=lookback_days)).to_pydatetime()
    rows = nav.find({"date": {"$gte": lo, "$lte": hi}},
                    {"_id": 0, "id": 1, "date": 1, "nav": 1, "scheme_nav_name": 1, "fund_house": 1,
                     "Scheme Category": 1})
    df = pd.DataFrame(list(rows))
    return df.sort_values("date").groupby("id").last()


def _clean_category(c):
    return (c.fillna("").str.replace(r"^Equity Schemes? - ", "", regex=True)
            .str.replace("ELSS- Tax Saver Fund", "ELSS").str.strip())


def _growth_plans(name):
    """Boolean mask: growth-option plans (see NOT_GROWTH_RE / PAYOUT_FREQ_RE)."""
    has_growth = name.str.contains(GROWTH_RE)
    return ~name.str.contains(NOT_GROWTH_RE) & (has_growth | ~name.str.contains(PAYOUT_FREQ_RE))


def returns(start, end, universe="diversified", plan="direct", n=10, bench=DEFAULT_BENCH, category=None):
    """
    Point-to-point NAV return per plan, start -> end (each = last NAV within 7 days on/before).
    Growth option only, one plan type (direct/regular), so each scheme appears once.
    Category is taken from the END row (the Aug-2026 SEBI re-categorisation renamed labels).
    """
    b, e = _nav_asof(start), _nav_asof(end)
    j = e.join(b[["nav", "date"]], rsuffix="0", how="inner")
    j = j[(j.nav > 0) & (j.nav0 > 0)].copy()
    j["ret_pct"] = (j.nav / j.nav0 - 1) * 100
    bench_ret = float(j.at[bench, "ret_pct"]) if bench in j.index else None
    name = j["scheme_nav_name"].fillna("")
    is_direct = name.str.contains("direct", case=False)
    keep = _growth_plans(name)
    keep &= is_direct if plan == "direct" else ~is_direct
    keep &= UNIVERSES[universe](j["Scheme Category"].fillna(""))
    if category:
        keep &= j["Scheme Category"].fillna("").str.contains(category, case=False, regex=True)
    u = j[keep].copy()
    # One plan per scheme: if an AMC still lists two growth-like direct plans, keep the one named "Growth"
    u["_base"] = u["fund_house"].fillna("") + "|" + u["scheme_nav_name"].str.lower().str.split("direct").str[0] \
        .str.replace(r"[^a-z0-9]", "", regex=True)
    u["_g"] = u["scheme_nav_name"].str.contains(GROWTH_RE)
    dupes = int(u.duplicated("_base").sum())
    u = u.sort_values("_g", ascending=False).drop_duplicates("_base").drop(columns=["_base", "_g"])
    u["category"] = _clean_category(u["Scheme Category"])
    u = u.sort_values("ret_pct", ascending=False)
    cols = ["scheme_nav_name", "fund_house", "category", "nav0", "nav", "ret_pct"]
    top = u[cols].head(n).reset_index().rename(columns={"id": "amfi_code"})
    bottom = u[cols].tail(5).reset_index().rename(columns={"id": "amfi_code"})
    by_cat = (u.groupby("category")["ret_pct"].agg(["count", "median", "max"])
              .sort_values("median", ascending=False).round(2).reset_index())
    meta = {
        "start_requested": start, "end_requested": end,
        "start_nav_date": str(u["date0"].mode().iat[0].date()), "end_nav_date": str(u["date"].mode().iat[0].date()),
        "universe": universe, "category_filter": category, "plan": f"{plan} / growth",
        "duplicate_plans_dropped": dupes,
        "funds_in_universe": int(len(u)),
        "median_ret_pct": round(float(u.ret_pct.median()), 2),
        "pct_positive": round(float((u.ret_pct > 0).mean() * 100), 1),
        "benchmark": f"{bench} {e.at[bench, 'scheme_nav_name'] if bench in e.index else '?'}",
        "benchmark_ret_pct": round(bench_ret, 2) if bench_ret is not None else None,
        "funds_beating_benchmark": int((u.ret_pct > bench_ret).sum()) if bench_ret is not None else None,
        "top10_cutoff_ret_pct": round(float(u.ret_pct.iloc[min(n, len(u)) - 1]), 2),
        "by_category": by_cat.to_dict("records"),
        "bottom5": bottom.round(2).to_dict("records"),
    }
    return top.round(2), meta


def aum_ranking(m, n=10, category=None):
    """Largest schemes by AUM from the month's portfolio disclosures (aum_cr = scheme AUM as disclosed)."""
    lo, hi = _bounds(m)
    col = _client().MUTUALFUND_DATA.MFDetails
    rows = col.aggregate([
        {"$match": {"date": {"$gte": lo, "$lt": hi}}},
        {"$group": {"_id": {"f": "$fundHouse", "s": "$schemeName"}, "aum_max": {"$max": "$aum_cr"},
                    "aum_min": {"$min": "$aum_cr"}, "code": {"$first": "$amfiCode"},
                    "holdings_cr": {"$sum": "$stock_aum_cr"}}},
    ], allowDiskUse=True)
    df = pd.DataFrame([{**r["_id"], **{k: v for k, v in r.items() if k != "_id"}} for r in rows])
    df = df.rename(columns={"f": "amc", "s": "scheme", "aum_max": "aum_cr"}).dropna(subset=["aum_cr"])
    df["aum_consistent"] = (df["aum_cr"] - df["aum_min"]).abs() < 0.01
    df["holdings_to_aum"] = (df["holdings_cr"] / df["aum_cr"]).round(3)
    cats = scheme_categories()
    df["category"] = df["code"].astype(str).map(cats)
    if category:
        # Category from the AMFI code; schemes renamed in Aug-2026 lost their code, so fall
        # back to the scheme name (excluding index funds / ETFs, which are a different category).
        by_cat = df["category"].fillna("").str.contains(category, case=False, regex=True)
        by_name = df["category"].isna() & df["scheme"].str.contains(category, case=False, regex=True) \
            & ~df["scheme"].str.contains(PASSIVE_RE)
        df = df[by_cat | by_name].copy()
    df = df.sort_values("aum_cr", ascending=False)
    total = float(df["aum_cr"].sum())
    top = df.head(n).copy()
    top["share_of_reported_aum_pct"] = top["aum_cr"] / total * 100
    top["passive"] = top["scheme"].str.contains(PASSIVE_RE)
    meta = {"month": m, "category_filter": category, "schemes_reported": int(len(df)), "reported_aum_cr": round(total, 0),
            "top_n_aum_cr": round(float(top.aum_cr.sum()), 0),
            "top_n_share_pct": round(float(top.aum_cr.sum()) / total * 100, 2),
            "flags_inconsistent_aum": top.loc[~top.aum_consistent, "scheme"].tolist(),
            "flags_holdings_mismatch": top.loc[(top.holdings_to_aum < 0.9) | (top.holdings_to_aum > 1.1), "scheme"].tolist()}
    cols = ["amc", "scheme", "code", "category", "aum_cr", "share_of_reported_aum_pct", "passive", "holdings_to_aum"]
    return top[cols].reset_index(drop=True).round(2), meta


def _show(title, df, meta):
    print(f"\n== {title}")
    for k, v in meta.items():
        if not isinstance(v, (list, dict)):
            print(f"   {k}: {v}")
    if df is not None:
        with pd.option_context("display.max_rows", 200, "display.width", 200, "display.float_format", "{:,.2f}".format):
            print(df.to_string(index=False))
    for k, v in meta.items():
        if isinstance(v, (list, dict)) and v:
            print(f"   {k}:")
            for r in (v if isinstance(v, list) else [v]):
                print("     ", r)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["months", "health", "top", "flows", "sectors", "caps", "stock", "returns", "aum"])
    ap.add_argument("--month")
    ap.add_argument("--prev")
    ap.add_argument("--n", type=int, default=15)
    ap.add_argument("--q")
    ap.add_argument("--active-only", action="store_true")
    ap.add_argument("--start", help="returns: start date YYYY-MM-DD (e.g. 2025-12-31 for YTD)")
    ap.add_argument("--end", help="returns: end date YYYY-MM-DD (default: latest NAV date)")
    ap.add_argument("--universe", default="diversified", choices=list(UNIVERSES))
    ap.add_argument("--plan", default="direct", choices=["direct", "regular"])
    ap.add_argument("--bench", default=DEFAULT_BENCH, help="benchmark plan code for returns")
    ap.add_argument("--category", help="regex on AMFI category, e.g. 'Small Cap' (returns, aum)")
    ap.add_argument("--json", help="save the facts to this JSON file (evidence for the post)")
    a = ap.parse_args()

    if a.cmd == "months":
        print(" ".join(str(p) for p in months()))
        return
    m = a.month or str(months()[-1])
    out = {}
    if a.cmd == "health":
        h = health(m)
        _show(f"Data health {m}", pd.DataFrame(h["missing_by_amc"]) if h["missing_by_amc"] else None,
              {k: v for k, v in h.items() if k != "missing_by_amc"})
        out = h
    elif a.cmd == "top":
        df, meta = top_holdings(m, a.n); _show(f"Top MF stock holdings {m}", df, meta)
        out = {**meta, "rows": df.to_dict("records")}
    elif a.cmd == "flows":
        buys, sells, meta = flows(m, a.prev, a.n, a.active_only)
        _show(f"Net BUYING {meta['prev']} -> {m}", buys, meta)
        _show(f"Net SELLING {meta['prev']} -> {m}", sells, {})
        out = {**meta, "buys": buys.to_dict("records"), "sells": sells.to_dict("records")}
    elif a.cmd == "sectors":
        df, meta = sectors(m, a.n); _show(f"Industry mix {m}", df, meta)
        out = {**meta, "rows": df.to_dict("records")}
    elif a.cmd == "caps":
        df, meta = caps(m); _show(f"Market-cap mix {m}", df, meta)
        out = {**meta, "rows": df.to_dict("records")}
    elif a.cmd == "returns":
        if not a.start:
            sys.exit("--start required, e.g. --start 2025-12-31")
        end = a.end or str(_client().MUTUALFUND_NAV.NAV_Merged_Data.find_one(sort=[("date", -1)])["date"].date())
        df, meta = returns(a.start, end, a.universe, a.plan, a.n, a.bench, a.category)
        _show(f"Top {a.n} {a.universe} funds by return {meta['start_nav_date']} -> {meta['end_nav_date']}", df, meta)
        out = {**meta, "rows": df.to_dict("records")}
    elif a.cmd == "aum":
        df, meta = aum_ranking(m, a.n, a.category); _show(f"Top {a.n} schemes by AUM {m}", df, meta)
        out = {**meta, "rows": df.to_dict("records")}
    elif a.cmd == "stock":
        if not a.q:
            sys.exit("--q required")
        df, meta = stock(m, a.q); _show(f"{meta['stock']} in MF portfolios {m}", df, meta)
        out = {**meta, "by_amc": df.to_dict("records")}
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        with open(a.json, "w") as f:
            json.dump(out, f, indent=2, default=str)
        print(f"\nsaved -> {a.json}")


if __name__ == "__main__":
    main()
