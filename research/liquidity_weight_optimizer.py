"""Optimize liquidity score weights using Optuna.

Target: avg_monthly_qty (actual units moved = true liquidity).
Features: txn_volume_pct, consistency_pct, trend_pct, listing_ratio_pct.
Objective: maximize Spearman rank correlation between weighted composite and target.
"""

import json
import logging
import sys
from itertools import groupby

import numpy as np
import optuna
from scipy.stats import spearmanr

sys.path.insert(0, "/Users/wilson/prog/bws")

from db.connection import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress optuna noise
optuna.logging.set_verbosity(optuna.logging.WARNING)


def _percentile(all_values: list[float], target: float) -> float:
    n = len(all_values)
    if n <= 1:
        return 50.0
    below = sum(1 for v in all_values if v < target)
    equal = sum(1 for v in all_values if v == target)
    return (below + 0.5 * equal) / n * 100.0


def load_data() -> dict[str, dict]:
    """Load BrickLink monthly sales + listing data, compute per-item stats."""
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT item_id, year, month, times_sold, total_quantity
        FROM bricklink_monthly_sales
        WHERE condition = 'new'
        ORDER BY item_id, year, month
        """,
    ).fetchall()

    # Listing snapshot
    listing_map: dict[str, tuple[int, int]] = {}
    snap_rows = conn.execute(
        """
        SELECT DISTINCT ON (item_id) item_id, current_new
        FROM bricklink_price_history
        WHERE current_new IS NOT NULL
        ORDER BY item_id, scraped_at DESC
        """,
    ).fetchall()
    for sr in snap_rows:
        raw_box = sr[1]
        if isinstance(raw_box, str):
            raw_box = json.loads(raw_box)
        if isinstance(raw_box, dict):
            lots = raw_box.get("total_lots")
            qty = raw_box.get("total_qty")
            if lots is not None or qty is not None:
                listing_map[sr[0]] = (int(lots or 0), int(qty or 0))

    conn.close()

    all_stats: dict[str, dict] = {}
    for item_id, group in groupby(rows, key=lambda r: r[0]):
        records = list(group)
        sn = item_id.removesuffix("-1")
        txns = [r[3] or 0 for r in records]
        qtys = [r[4] or 0 for r in records]

        total_months = len(txns)
        if total_months == 0:
            continue

        months_with_sales = sum(1 for c in txns if c > 0)
        total_txns = sum(txns)
        total_qty = sum(qtys)
        consistency = months_with_sales / total_months
        avg_monthly_txns = total_txns / total_months
        avg_monthly_qty = total_qty / total_months

        recent = txns[-6:] if len(txns) >= 6 else txns
        older = txns[:-6] if len(txns) > 6 else []
        recent_avg = sum(recent) / len(recent) if recent else 0
        older_avg = sum(older) / len(older) if older else 0
        trend_ratio = (recent_avg / older_avg) if older_avg > 0 else None

        listing_ratio = None
        listing = listing_map.get(item_id)
        if listing and recent_avg > 0:
            listing_ratio = listing[0] / recent_avg

        all_stats[sn] = {
            "avg_monthly_txns": avg_monthly_txns,
            "avg_monthly_qty": avg_monthly_qty,
            "consistency": consistency,
            "trend_ratio": trend_ratio,
            "listing_ratio": listing_ratio,
            "total_months": total_months,
        }

    return all_stats


def compute_percentiles(all_stats: dict[str, dict]) -> dict[str, dict]:
    """Compute percentile ranks for each metric."""
    vol_vals = [v["avg_monthly_txns"] for v in all_stats.values()]
    con_vals = [v["consistency"] for v in all_stats.values()]
    trend_vals = [
        v["trend_ratio"]
        for v in all_stats.values()
        if v.get("trend_ratio") is not None
    ]
    lr_vals = [
        v["listing_ratio"]
        for v in all_stats.values()
        if v.get("listing_ratio") is not None
    ]
    qty_vals = [v["avg_monthly_qty"] for v in all_stats.values()]

    result: dict[str, dict] = {}
    for k, v in all_stats.items():
        v_pct = _percentile(vol_vals, v["avg_monthly_txns"])
        c_pct = _percentile(con_vals, v["consistency"])
        t_pct = (
            _percentile(trend_vals, v["trend_ratio"])
            if v.get("trend_ratio") is not None
            else None
        )
        # Invert: lower listing ratio = better liquidity
        lr_pct = (
            100.0 - _percentile(lr_vals, v["listing_ratio"])
            if v.get("listing_ratio") is not None
            else None
        )
        q_pct = _percentile(qty_vals, v["avg_monthly_qty"])

        result[k] = {
            "volume_pct": v_pct,
            "consistency_pct": c_pct,
            "trend_pct": t_pct,
            "listing_ratio_pct": lr_pct,
            "qty_pct": q_pct,
            "avg_monthly_qty": v["avg_monthly_qty"],
        }

    return result


def objective(trial: optuna.Trial, items: list[dict]) -> float:
    """Optuna objective: maximize Spearman correlation with avg_monthly_qty."""
    # Sample weights (they'll be normalized to sum to 1)
    w_vol = trial.suggest_float("w_volume", 0.0, 1.0)
    w_con = trial.suggest_float("w_consistency", 0.0, 1.0)
    w_trend = trial.suggest_float("w_trend", 0.0, 1.0)
    w_lr = trial.suggest_float("w_listing_ratio", 0.0, 1.0)

    total_w = w_vol + w_con + w_trend + w_lr
    if total_w < 0.01:
        return -1.0

    # Normalize
    w_vol /= total_w
    w_con /= total_w
    w_trend /= total_w
    w_lr /= total_w

    composites = []
    targets = []
    for item in items:
        # Skip items missing trend or listing ratio
        if item["trend_pct"] is None or item["listing_ratio_pct"] is None:
            continue

        comp = (
            w_vol * item["volume_pct"]
            + w_con * item["consistency_pct"]
            + w_trend * item["trend_pct"]
            + w_lr * item["listing_ratio_pct"]
        )
        composites.append(comp)
        targets.append(item["avg_monthly_qty"])

    if len(composites) < 50:
        return -1.0

    rho, _ = spearmanr(composites, targets)
    return rho


def main() -> None:
    logger.info("Loading BrickLink sales data...")
    all_stats = load_data()
    logger.info(f"Loaded {len(all_stats)} items with monthly sales")

    logger.info("Computing percentiles...")
    pct_data = compute_percentiles(all_stats)
    items = list(pct_data.values())

    # Filter to items with all metrics
    complete = [i for i in items if i["trend_pct"] is not None and i["listing_ratio_pct"] is not None]
    logger.info(f"Items with all 4 features: {len(complete)}")

    # --- Current baseline ---
    baseline_composites = []
    baseline_targets = []
    for item in complete:
        comp = item["volume_pct"] * 0.5 + item["consistency_pct"] * 0.3 + item["trend_pct"] * 0.2
        baseline_composites.append(comp)
        baseline_targets.append(item["avg_monthly_qty"])

    baseline_rho, baseline_p = spearmanr(baseline_composites, baseline_targets)
    print(f"\n{'='*60}")
    print(f"BASELINE (vol=50%, con=30%, trend=20%, lr=0%)")
    print(f"  Spearman rho = {baseline_rho:.4f}  (p={baseline_p:.2e})")
    print(f"{'='*60}")

    # --- Also test with listing_ratio added at current weights ---
    lr_composites = []
    for item in complete:
        comp = (
            item["volume_pct"] * 0.4
            + item["consistency_pct"] * 0.25
            + item["trend_pct"] * 0.15
            + item["listing_ratio_pct"] * 0.2
        )
        lr_composites.append(comp)
    lr_rho, lr_p = spearmanr(lr_composites, baseline_targets)
    print(f"\nNAIVE 4-FEATURE (vol=40%, con=25%, trend=15%, lr=20%)")
    print(f"  Spearman rho = {lr_rho:.4f}  (p={lr_p:.2e})")

    # --- Optuna optimization ---
    logger.info("Running Optuna optimization (1000 trials)...")
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(lambda trial: objective(trial, complete), n_trials=1000, show_progress_bar=True)

    best = study.best_trial
    raw = {
        "w_volume": best.params["w_volume"],
        "w_consistency": best.params["w_consistency"],
        "w_trend": best.params["w_trend"],
        "w_listing_ratio": best.params["w_listing_ratio"],
    }
    total = sum(raw.values())
    normalized = {k: round(v / total, 3) for k, v in raw.items()}

    print(f"\n{'='*60}")
    print(f"OPTIMIZED WEIGHTS (Optuna, 1000 trials)")
    print(f"  Spearman rho = {best.value:.4f}")
    for k, v in normalized.items():
        print(f"  {k:20s} = {v:.1%}")
    print(f"{'='*60}")

    # --- Improvement ---
    improvement = best.value - baseline_rho
    print(f"\nImprovement: {improvement:+.4f} rho ({improvement/abs(baseline_rho)*100:+.1f}%)")

    # --- Top/bottom analysis ---
    print(f"\n--- Validation: top-20 vs bottom-20 by optimized score ---")
    scored = []
    for k, item in pct_data.items():
        if item["trend_pct"] is None or item["listing_ratio_pct"] is None:
            continue
        comp = (
            normalized["w_volume"] * item["volume_pct"]
            + normalized["w_consistency"] * item["consistency_pct"]
            + normalized["w_trend"] * item["trend_pct"]
            + normalized["w_listing_ratio"] * item["listing_ratio_pct"]
        )
        scored.append((k, comp, item["avg_monthly_qty"]))

    scored.sort(key=lambda x: x[1], reverse=True)

    print(f"\nTop 20 (highest liquidity score):")
    print(f"  {'Set':<12} {'Score':>6} {'Avg Qty/Mo':>10}")
    for sn, sc, qty in scored[:20]:
        print(f"  {sn:<12} {sc:>6.1f} {qty:>10.1f}")

    top_20_qty = np.mean([x[2] for x in scored[:20]])
    bottom_20_qty = np.mean([x[2] for x in scored[-20:]])

    print(f"\nBottom 20 (lowest liquidity score):")
    print(f"  {'Set':<12} {'Score':>6} {'Avg Qty/Mo':>10}")
    for sn, sc, qty in scored[-20:]:
        print(f"  {sn:<12} {sc:>6.1f} {qty:>10.1f}")

    print(f"\nTop-20 avg qty/mo: {top_20_qty:.1f}")
    print(f"Bottom-20 avg qty/mo: {bottom_20_qty:.1f}")
    print(f"Ratio: {top_20_qty / bottom_20_qty:.1f}x" if bottom_20_qty > 0 else "Bottom has 0 qty")

    # --- Feature importance via ablation ---
    print(f"\n--- Feature ablation (drop one at a time) ---")
    features = ["w_volume", "w_consistency", "w_trend", "w_listing_ratio"]
    for drop in features:
        ablated = {k: v for k, v in normalized.items() if k != drop}
        ab_total = sum(ablated.values())
        if ab_total < 0.01:
            continue
        ablated = {k: v / ab_total for k, v in ablated.items()}

        ab_composites = []
        ab_targets = []
        for item in complete:
            comp = sum(
                ablated.get(f, 0) * item[f.replace("w_", "") + "_pct"]
                for f in features
                if f != drop
            )
            ab_composites.append(comp)
            ab_targets.append(item["avg_monthly_qty"])

        ab_rho, _ = spearmanr(ab_composites, ab_targets)
        delta = best.value - ab_rho
        print(f"  Drop {drop:20s}: rho={ab_rho:.4f}  (loss={delta:+.4f})")


if __name__ == "__main__":
    main()
