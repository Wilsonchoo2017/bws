#!/usr/bin/env python3
"""Scorecard for the current growth-classifier signal vs ground truth.

Runs in ~60s with no retraining. Joins live scored predictions (from
the in-memory growth_provider) against the effective-APR ground truth
(from load_bl_ground_truth), then reports three views:

  1. Category scorecard — per bucket (GREAT/GOOD/WORST/SKIP), what
     actually happens when the model says X. This is precision in
     practical terms.
  2. Portfolio simulator — top-N per category by confidence,
     capital-weighted realized APR. Benchmarks against "buy all
     retired" baseline. Tells you whether following the signal
     actually makes money.
  3. Liquidity slice — same scorecard segmented by trailing-90d
     sales velocity tier (fast / steady / slow). Shows whether the
     proposed MAYBE/liquidity reshape is pulling weight before we
     build it.

Usage:
    ./scripts/evaluate_signal.py
    ./scripts/evaluate_signal.py --top 20
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("bws.evaluate")


# Liquidity tier boundaries (trailing-90d sales per month)
LIQ_FAST = 3.0
LIQ_STEADY = 1.0


def _liq_tier(v: float | None) -> str:
    if v is None or v < 0:
        return "unknown"
    if v >= LIQ_FAST:
        return "fast"
    if v >= LIQ_STEADY:
        return "steady"
    return "slow"


def _fmt_pct(xs: list[float], thr: float) -> str:
    if not xs:
        return "  n/a"
    return f"{sum(1 for x in xs if x >= thr) / len(xs) * 100:5.1f}%"


def _fmt_neg(xs: list[float]) -> str:
    if not xs:
        return "  n/a"
    return f"{sum(1 for x in xs if x < 0) / len(xs) * 100:5.1f}%"


def _scorecard_row(label: str, aprs: list[float]) -> str:
    n = len(aprs)
    if n == 0:
        return f"  {label:12} n=   0  | mean=  n/a  median=  n/a  | ≥10%=  n/a  ≥20%=  n/a  neg=  n/a"
    return (
        f"  {label:12} n={n:4d}  | "
        f"mean={mean(aprs):6.2f}%  median={median(aprs):6.2f}%  | "
        f"≥10%={_fmt_pct(aprs, 10)}  ≥20%={_fmt_pct(aprs, 20)}  neg={_fmt_neg(aprs)}"
    )


def run_scorecard(top: int) -> None:
    from db.pg.engine import get_engine
    from services.ml.growth.sales_velocity_features import load_sales_velocity_features
    from services.ml.pg_queries import load_bl_ground_truth
    from services.scoring.growth_provider import growth_provider

    print("Loading ground truth (effective APR)…")
    engine = get_engine()
    gt = load_bl_ground_truth(engine)
    print(f"  {len(gt):,} retired sets with ground-truth effective APR\n")

    print("Loading velocity (trailing-90d sales/month)…")
    vel_df = load_sales_velocity_features(engine)
    vel = {
        str(sn): float(v)
        for sn, v in zip(vel_df["set_number"], vel_df["bl_sales_per_month_recent"])
        if v is not None
    }
    print(f"  {len(vel):,} sets with velocity data\n")

    print("Scoring all sets via growth_provider…")
    scored = growth_provider.score_all()
    print(f"  {len(scored):,} sets scored\n")

    # Join ground truth + prediction
    joined: list[dict] = []
    for sn, apr in gt.items():
        pred = scored.get(sn)
        if pred is None:
            continue
        joined.append(
            {
                "sn": sn,
                "apr": apr,
                "cat": pred.get("buy_category") or "SKIP",
                "p_avoid": pred.get("avoid_probability") or 0.0,
                "p_great": pred.get("great_buy_probability") or 0.0,
                "p_good": pred.get("good_buy_probability") or 0.0,
                "vel": vel.get(sn),
                "entry_ok": pred.get("entry_price_ok"),
                "action": pred.get("recommended_action"),
                "price_ratio": pred.get("price_vs_rrp_ratio"),
            }
        )
    print(f"  {len(joined):,} sets with both prediction and ground truth\n")

    if not joined:
        print("No joined sets — nothing to evaluate.")
        return

    # --------------------------------------------------------------
    # 1. Category scorecard
    # --------------------------------------------------------------
    print("=" * 80)
    print("1. CATEGORY SCORECARD  (what actually happens when the model says X)")
    print("=" * 80)

    for cat in ("GREAT", "GOOD", "SKIP", "WORST"):
        aprs = [r["apr"] for r in joined if r["cat"] == cat]
        print(_scorecard_row(cat, aprs))

    all_aprs = [r["apr"] for r in joined]
    print(_scorecard_row("BASELINE", all_aprs))
    print()

    # --------------------------------------------------------------
    # 2. Portfolio simulator — top-N by confidence per category
    # --------------------------------------------------------------
    print("=" * 80)
    print(f"2. PORTFOLIO SIMULATOR  (top-{top} per category, equal-weight realized APR)")
    print("=" * 80)

    def _topn(cat: str, score_key: str) -> list[dict]:
        pool = [r for r in joined if r["cat"] == cat]
        pool.sort(key=lambda r: r[score_key], reverse=True)
        return pool[:top]

    great_picks = _topn("GREAT", "p_great")
    good_picks = _topn("GOOD", "p_good")
    combined = great_picks + good_picks

    for label, picks in (
        (f"Top-{top} GREAT by p_great", great_picks),
        (f"Top-{top} GOOD  by p_good ", good_picks),
        (f"Combined {len(combined)} picks", combined),
    ):
        aprs = [r["apr"] for r in picks]
        print(_scorecard_row(label, aprs))
    print()

    # --------------------------------------------------------------
    # 3. Liquidity slice — each category segmented by velocity tier
    # --------------------------------------------------------------
    print("=" * 80)
    print("3. LIQUIDITY SLICE  (category × trailing-90d velocity tier)")
    print("=" * 80)
    print(f"  Tiers: fast ≥{LIQ_FAST}/mo  |  steady ≥{LIQ_STEADY}/mo  |  slow <{LIQ_STEADY}/mo  |  unknown = no velocity row")
    print()

    for cat in ("GREAT", "GOOD", "WORST"):
        print(f"  [{cat}]")
        for tier in ("fast", "steady", "slow", "unknown"):
            aprs = [
                r["apr"] for r in joined
                if r["cat"] == cat and _liq_tier(r["vel"]) == tier
            ]
            print(_scorecard_row(f"  {tier}", aprs))
        print()

    # --------------------------------------------------------------
    # 4. Reshape preview — what WOULD happen with the promotion ladder
    # --------------------------------------------------------------
    print("=" * 80)
    print("4. RESHAPE PREVIEW  (simulates the proposed liquidity promotion ladder)")
    print("=" * 80)
    print("  Rule: GOOD + fast → GREAT; GREAT + slow → GOOD; everything else unchanged.")
    print()

    reshaped: dict[str, list[float]] = {"GREAT": [], "GOOD": [], "WORST": [], "SKIP": []}
    for r in joined:
        tier = _liq_tier(r["vel"])
        cat = r["cat"]
        if cat == "GOOD" and tier == "fast":
            cat = "GREAT"
        elif cat == "GREAT" and tier == "slow":
            cat = "GOOD"
        reshaped.setdefault(cat, []).append(r["apr"])

    for cat in ("GREAT", "GOOD", "SKIP", "WORST"):
        print(_scorecard_row(cat, reshaped.get(cat, [])))
    print()

    # --------------------------------------------------------------
    # 5. Entry-price filter validation
    # --------------------------------------------------------------
    print("=" * 80)
    print("5. ENTRY-PRICE FILTER  (does the BUY bucket beat the WAIT bucket?)")
    print("=" * 80)
    print("  Gate: GREAT at ≤1.05× RRP, GOOD at ≤1.00× RRP.")
    print()

    for cat in ("GREAT", "GOOD"):
        print(f"  [{cat}]")
        buy = [r["apr"] for r in joined if r["cat"] == cat and r.get("action") == "BUY"]
        wait = [r["apr"] for r in joined if r["cat"] == cat and r.get("action") == "WAIT"]
        unk = [r["apr"] for r in joined if r["cat"] == cat and r.get("price_ratio") is None]
        print(_scorecard_row("  BUY", buy))
        print(_scorecard_row("  WAIT", wait))
        print(_scorecard_row("  no price", unk))
        if buy and wait:
            delta = mean(buy) - mean(wait)
            print(f"  BUY mean − WAIT mean = {delta:+.2f}pp")
        print()

    # --------------------------------------------------------------
    # Decision signal
    # --------------------------------------------------------------
    great_aprs = [r["apr"] for r in joined if r["cat"] == "GREAT"]
    great_mean = mean(great_aprs) if great_aprs else 0.0
    great_win = (
        sum(1 for a in great_aprs if a >= 10.0) / len(great_aprs) * 100.0
        if great_aprs else 0.0
    )
    print("=" * 80)
    print("DECISION SIGNAL")
    print("=" * 80)
    print(f"  GREAT bucket mean APR:   {great_mean:.2f}%   (ship gate ≥15%)")
    print(f"  GREAT bucket win ≥10%:   {great_win:.1f}%    (ship gate ≥80%)")
    verdict = "SHIP" if great_mean >= 15.0 and great_win >= 80.0 else "CALIBRATE"
    print(f"  Verdict:                 {verdict}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scorecard for the growth classifier signal")
    parser.add_argument("--top", type=int, default=10, help="Portfolio top-N per category")
    args = parser.parse_args()
    run_scorecard(args.top)


if __name__ == "__main__":
    main()
