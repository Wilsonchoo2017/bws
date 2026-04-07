"""CLI entry point for running backtests.

Usage:
    python -m services.backtesting.runner
"""

import sys

import pandas as pd

from services.backtesting.analysis import (
    AnalysisResults,
    analyze_strategy,
    trades_to_dataframe,
)
from services.backtesting.engine import run_backtest
from services.backtesting.types import SIGNAL_NAMES, BacktestConfig


def print_header(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_subheader(title: str) -> None:
    """Print a subsection header."""
    print(f"\n--- {title} ---")


def print_correlations(results: AnalysisResults, strategy_name: str) -> None:
    """Print correlation matrix for a strategy."""
    print_subheader(f"Signal Correlations ({strategy_name})")

    if results.correlations.empty:
        print("  No data available for correlation analysis.")
        return

    print(f"  Sample size: {results.sample_size} trades")
    print()

    # Format and print
    for signal in results.correlations.index:
        values = []
        for col in results.correlations.columns:
            val = results.correlations.loc[signal, col]
            if pd.isna(val):
                values.append("  N/A  ")
            else:
                values.append(f" {val:+.3f} ")
        print(f"  {signal:25s} {''.join(values)}")

    # Print column headers
    cols = results.correlations.columns.tolist()
    header = " " * 27 + "".join(f" {c:>7s}" for c in cols)
    print(f"\n  {'Legend:':25s}")
    for col in cols:
        print(f"    {col}")


def print_feature_importance(results: AnalysisResults, strategy_name: str) -> None:
    """Print feature importance ranking."""
    print_subheader(f"Signal Importance Ranking ({strategy_name})")

    if results.feature_importance is None:
        print("  Insufficient data for feature importance analysis.")
        print("  Need: sklearn installed + 10+ trade samples.")
        return

    print(f"  Sample size: {results.sample_size} trades")
    print()
    print(f"  {'Rank':>4s}  {'Signal':25s}  {'Importance':>10s}  {'Bar'}")
    print(f"  {'----':>4s}  {'-------------------------':25s}  {'----------':>10s}  {'---'}")

    for rank, (signal, importance) in enumerate(
        results.feature_importance.items(), 1
    ):
        bar_len = int(importance * 50)
        bar = "#" * bar_len
        print(f"  {rank:4d}  {signal:25s}  {importance:10.4f}  {bar}")


def print_quintile_analysis(results: AnalysisResults, strategy_name: str) -> None:
    """Print quintile return analysis for top signals."""
    print_subheader(f"Quintile Returns ({strategy_name})")

    if not results.quintile_returns:
        print("  No quintile data available.")
        return

    # Show top 5 signals by quintile spread
    spreads = {}
    for signal, qt_df in results.quintile_returns.items():
        if len(qt_df) >= 2:
            spreads[signal] = qt_df["median"].iloc[-1] - qt_df["median"].iloc[0]

    sorted_signals = sorted(spreads.items(), key=lambda x: abs(x[1]), reverse=True)

    for signal, spread in sorted_signals[:5]:
        qt_df = results.quintile_returns[signal]
        print(f"\n  {signal} (spread: {spread:+.1%}):")
        for quintile, row in qt_df.iterrows():
            median_ret = row["median"]
            count = int(row["count"])
            bar_len = max(0, int(median_ret * 100))
            bar = "+" * min(bar_len, 30)
            if median_ret < 0:
                bar = "-" * min(abs(int(median_ret * 100)), 30)
            print(f"    {str(quintile):12s}  median={median_ret:+.1%}  n={count:3d}  {bar}")


def print_combinations(results: AnalysisResults, strategy_name: str) -> None:
    """Print best signal combinations."""
    print_subheader(f"Best Signal Combinations ({strategy_name})")

    if not results.best_combinations:
        print("  No combinations found.")
        return

    for i, combo in enumerate(results.best_combinations, 1):
        sig_a, sig_b = combo["signals"]
        corr = combo["correlation"]
        n = combo["sample_size"]
        print(f"  {i}. {sig_a} + {sig_b}")
        print(f"     Correlation: {corr:+.3f}  (n={n})")


def print_data_summary(df: pd.DataFrame) -> None:
    """Print summary of available data."""
    print_header("DATA SUMMARY")

    print(f"  Total trade samples: {len(df)}")
    print(f"  Unique items: {df['item_id'].nunique()}")

    # Return coverage
    return_cols = [c for c in df.columns if c.startswith("return_")]
    print(f"\n  Return horizon coverage:")
    for col in return_cols:
        count = df[col].notna().sum()
        pct = count / len(df) * 100 if len(df) > 0 else 0
        print(f"    {col:25s}  {count:5d} samples ({pct:.0f}%)")

    # Signal coverage
    print(f"\n  Signal coverage:")
    for signal in SIGNAL_NAMES:
        if signal in df.columns:
            count = df[signal].notna().sum()
            pct = count / len(df) * 100 if len(df) > 0 else 0
            print(f"    {signal:25s}  {count:5d} samples ({pct:.0f}%)")


def print_verdict(
    flip_results: AnalysisResults,
    hold_results: AnalysisResults,
) -> None:
    """Print the final verdict: which signals matter for each strategy."""
    print_header("VERDICT: WHICH SIGNALS DRIVE VALUE?")

    print("\n  FOR FLIPPING (1-2 month horizon):")
    if flip_results.feature_importance is not None and len(flip_results.feature_importance) > 0:
        top_flip = flip_results.feature_importance.head(5)
        for rank, (signal, imp) in enumerate(top_flip.items(), 1):
            corr_val = _get_best_corr(flip_results.correlations, signal)
            direction = "higher=better" if corr_val >= 0 else "lower=better"
            print(f"    {rank}. {signal} (importance={imp:.3f}, {direction})")
    else:
        print("    Insufficient data - need more items and history.")

    print("\n  FOR HOLDING (1-3 year horizon):")
    if hold_results.feature_importance is not None and len(hold_results.feature_importance) > 0:
        top_hold = hold_results.feature_importance.head(5)
        for rank, (signal, imp) in enumerate(top_hold.items(), 1):
            corr_val = _get_best_corr(hold_results.correlations, signal)
            direction = "higher=better" if corr_val >= 0 else "lower=better"
            print(f"    {rank}. {signal} (importance={imp:.3f}, {direction})")
    else:
        print("    Insufficient data - need more items and history.")

    # Data sufficiency warning
    min_samples = min(flip_results.sample_size, hold_results.sample_size)
    if min_samples < 50:
        print(f"\n  WARNING: Only {min_samples} trade samples available.")
        print("  Results are directional, not statistically significant.")
        print("  Recommended: 200+ samples for reliable conclusions.")
        print("  Action: Add more items to bricklink_monthly_sales via scraping.")


def _get_best_corr(corr_df: pd.DataFrame, signal: str) -> float:
    """Get the highest absolute correlation for a signal across return columns."""
    if signal not in corr_df.index:
        return 0.0
    row = corr_df.loc[signal].dropna()
    if row.empty:
        return 0.0
    return float(row.iloc[row.abs().argmax()])


def main() -> None:
    """Run the backtesting pipeline."""
    sys.path.insert(0, ".")

    import shutil
    import tempfile

    from db.connection import get_connection

    print_header("LEGO INVESTMENT SIGNAL BACKTESTER")
    print("  Running walk-forward backtest...")

    conn = get_connection()
    config = BacktestConfig(min_history_months=3)
    trades = run_backtest(conn, config)

    if not trades:
        print("\n  No trades generated. Possible causes:")
        print("  - Not enough monthly sales data (need 6+ months per item)")
        print("  - No items match the condition filter")
        print("  Run: python -c \"from db.connection import get_connection; ...")
        print("  ... to check data availability.")
        return

    df = trades_to_dataframe(trades)
    print(f"\n  Generated {len(trades)} trade samples across {df['item_id'].nunique()} items.")

    # Print data summary
    print_data_summary(df)

    # Identify available return columns
    flip_returns = [c for c in df.columns if c.startswith("return_flip_")]
    hold_returns = [c for c in df.columns if c.startswith("return_hold_")]

    # Analyze flip strategy
    primary_flip = "return_flip_1m" if "return_flip_1m" in df.columns else (
        flip_returns[0] if flip_returns else None
    )
    primary_hold = "return_hold_12m" if "return_hold_12m" in df.columns else (
        hold_returns[0] if hold_returns else None
    )

    if primary_flip:
        print_header("STRATEGY A: FLIPPING")
        flip_results = analyze_strategy(df, flip_returns, primary_flip)
        print_correlations(flip_results, "Flipping")
        print_feature_importance(flip_results, "Flipping")
        print_quintile_analysis(flip_results, "Flipping")
        print_combinations(flip_results, "Flipping")
    else:
        flip_results = None
        print("\n  No flip return data available.")

    if primary_hold:
        print_header("STRATEGY B: HOLDING (1-3 YEARS)")
        hold_results = analyze_strategy(df, hold_returns, primary_hold)
        print_correlations(hold_results, "Holding")
        print_feature_importance(hold_results, "Holding")
        print_quintile_analysis(hold_results, "Holding")
        print_combinations(hold_results, "Holding")
    else:
        hold_results = None
        print("\n  No hold return data available.")

    # Print verdict
    if flip_results and hold_results:
        print_verdict(flip_results, hold_results)

    # Signal audit (optional)
    if "--audit" in sys.argv or "--optimize" in sys.argv:
        _run_signal_audit(df, primary_flip, primary_hold)

    # ML optimization (optional)
    if "--optimize" in sys.argv:
        _run_optimization(df)

    print(f"\n{'=' * 70}")
    print("  Backtest complete.")
    print(f"{'=' * 70}\n")


def _run_signal_audit(
    df: pd.DataFrame,
    primary_flip: str | None,
    primary_hold: str | None,
) -> None:
    """Run signal significance audit."""
    from services.backtesting.signal_audit import audit_signals, print_audit_report

    print_header("SIGNAL SIGNIFICANCE AUDIT")

    # Audit against flip returns (most data available)
    if primary_flip:
        flip_audit = audit_signals(df, primary_flip)
        print_audit_report(flip_audit)

    # Audit against hold returns if available
    if primary_hold:
        hold_valid = df[primary_hold].notna().sum()
        if hold_valid >= 10:
            hold_audit = audit_signals(df, primary_hold)
            print_audit_report(hold_audit)
        else:
            print(f"\n  Skipping hold audit: only {hold_valid} samples "
                  f"with {primary_hold} data (need 10+)")
            print("  Action: Scrape more BrickLink price history "
                  "to build 12+ month coverage per item.")


def _run_optimization(df: pd.DataFrame) -> None:
    """Run ML signal weight optimization on backtest results."""
    from config.kelly import SIGNAL_WEIGHTS
    from services.backtesting.evaluation import (
        evaluate_all_strategies,
        print_evaluation_report,
        print_weight_comparison,
    )
    from services.backtesting.features import engineer_features
    from services.backtesting.optimizer import (
        extract_signal_weights,
        optimize_weights,
    )
    from services.backtesting.returns import add_apr_columns, compute_best_apr

    print_header("ML SIGNAL WEIGHT OPTIMIZATION")

    # Step 1: Compute APR
    print("  Computing annualized returns (APR)...")
    df = add_apr_columns(df)
    df = compute_best_apr(df)

    apr_valid = df["best_hold_apr"].notna().sum()
    print(f"  Samples with hold APR: {apr_valid}")

    if apr_valid < 50:
        print("  WARNING: < 50 samples with APR data.")
        print("  Results will be directional only. Add more BrickLink history.")

    # Step 2: Engineer features
    print("  Engineering features...")
    df, feature_cols = engineer_features(df)
    print(f"  Feature count: {len(feature_cols)}")

    # Step 3: Train models
    print("  Training models (Ridge, Lasso, GBRT)...")
    results = optimize_weights(df, feature_cols)

    if not results:
        print("  Optimization failed: insufficient data.")
        return

    # Step 4: Print results per model
    for r in results:
        print_subheader(f"{r.model_name} Results")
        print(f"  Train R2: {r.train_score:.3f}  |  Test R2: {r.test_score:.3f}")
        print(f"  Test top-quintile APR: {r.test_apr_mean:+.1%}")
        print(f"  Test hit rate: {r.test_hit_rate:.0%}")
        print(f"  Test quintile spread: {r.test_quintile_spread:+.1%}")
        print(f"  Samples: train={r.n_train}, test={r.n_test}")

    # Step 5: Extract best model's weights and compare
    best = results[0]
    ml_weights = extract_signal_weights(best)

    print_subheader(f"Weight Comparison: Hand-tuned vs {best.model_name}")
    print_weight_comparison(dict(SIGNAL_WEIGHTS), ml_weights, best.model_name)

    # Step 6: Evaluate strategies side-by-side
    print_subheader("Strategy Comparison (on full dataset)")
    strategies = {
        "Hand-tuned": dict(SIGNAL_WEIGHTS),
        best.model_name: ml_weights,
    }
    metrics = evaluate_all_strategies(df, strategies, "best_hold_apr")
    print_evaluation_report(metrics)

    # Step 7: Print adoption instructions
    print("\n  To adopt ML weights, update config/kelly.py:")
    print(f"  ML_SIGNAL_WEIGHTS = {_format_weights(ml_weights)}")
    print(f'  ML_WEIGHTS_SOURCE = "{best.model_name}"')


def _format_weights(weights: dict[str, float]) -> str:
    """Format weights dict for copy-paste into config."""
    lines = ["{\n"]
    for signal in SIGNAL_NAMES:
        if signal in weights:
            lines.append(f'    "{signal}": {weights[signal]},\n')
    lines.append("}")
    return "".join(lines)


if __name__ == "__main__":
    main()
