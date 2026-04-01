"""CLI entry point for the ML pipeline.

Usage:
    python -m services.ml.runner materialize   # Build feature store
    python -m services.ml.runner select        # Run feature selection analysis
    python -m services.ml.runner train         # Train models
    python -m services.ml.runner predict       # Score retiring-soon sets
    python -m services.ml.runner evaluate      # Show model performance
    python -m services.ml.runner features      # List registered features
"""

import logging
import sys

from config.ml import MLPipelineConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run the ML pipeline CLI."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    config = MLPipelineConfig()

    if command == "features":
        _cmd_features()
    elif command == "materialize":
        _cmd_materialize(config)
    elif command == "select":
        _cmd_select(config)
    elif command == "train":
        _cmd_train(config)
    elif command == "predict":
        _cmd_predict()
    elif command == "evaluate":
        _cmd_evaluate()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


def _cmd_features() -> None:
    """List all registered features."""
    # Import to trigger registration
    import services.ml.feature_extractors  # noqa: F401
    from services.ml.feature_registry import get_all

    features = get_all()
    print(f"\nRegistered features: {len(features)}")
    print(f"{'Name':<30} {'Source':<30} {'Type':<10} {'Enabled':<8}")
    print("-" * 80)
    for f in features:
        status = "YES" if f.is_enabled else "NO"
        print(f"{f.name:<30} {f.source_table:<30} {f.dtype:<10} {status:<8}")


def _cmd_materialize(config: MLPipelineConfig) -> None:
    """Build or refresh the feature store."""
    from db.connection import get_connection
    from services.ml.feature_store import get_store_stats, materialize_features

    conn = get_connection()
    try:
        df = materialize_features(conn, config, force_refresh=True)
        print(f"\nMaterialized features for {len(df)} sets")

        stats = get_store_stats(conn)
        print("\nFeature store stats:")
        for key, val in stats.items():
            print(f"  {key}: {val}")
    finally:
        conn.close()


def _cmd_select(config: MLPipelineConfig) -> None:
    """Run feature selection analysis."""
    from db.connection import get_connection
    from services.ml.feature_selection import select_features
    from services.ml.feature_store import load_feature_store

    conn = get_connection()
    try:
        for horizon in config.target_horizons:
            df = load_feature_store(conn, horizon)
            if df.empty:
                print(f"\nNo data for {horizon}m horizon")
                continue

            exclude = {"set_number", "target_return", "target_profitable"}
            feature_cols = [c for c in df.columns if c not in exclude]

            result = select_features(df, "target_return", feature_cols, config)
            print(f"\n--- {horizon}m Horizon ---")
            print(f"Selected: {len(result.selected_features)}")
            print(f"Dropped:  {len(result.dropped_features)}")

            if "mutual_info" in result.method_results:
                mi = result.method_results["mutual_info"]
                top_mi = sorted(mi.items(), key=lambda x: x[1], reverse=True)[:10]
                print("\nTop 10 by Mutual Information:")
                for name, score in top_mi:
                    print(f"  {name:<30} {score:.4f}")

            if result.dropped_features:
                print(f"\nDropped: {', '.join(result.dropped_features[:10])}")
    finally:
        conn.close()


def _cmd_train(config: MLPipelineConfig) -> None:
    """Train models."""
    from db.connection import get_connection
    from services.ml.training import record_model_run, save_model, train_pipeline

    conn = get_connection()
    try:
        for horizon in config.target_horizons:
            print(f"\n=== Training {horizon}m horizon ===")

            # Regression
            reg_models = train_pipeline(conn, horizon, "regression", config)
            for m in reg_models:
                path = save_model(m, config.model_artifact_dir)
                record_model_run(conn, m, path)

            # Classification
            clf_models = train_pipeline(conn, horizon, "classification", config)
            for m in clf_models:
                path = save_model(m, config.model_artifact_dir)
                record_model_run(conn, m, path)

            total = len(reg_models) + len(clf_models)
            print(f"Trained {total} models for {horizon}m horizon")
    finally:
        conn.close()


def _cmd_predict() -> None:
    """Score sets approaching retirement."""
    from db.connection import get_connection
    from services.ml.prediction import predict_current_sets

    conn = get_connection()
    try:
        results = predict_current_sets(conn)
        if not results:
            print("No predictions generated")
            return

        print(f"\nPredictions for {len(results)} sets:")
        print(f"{'Set':<12} {'Title':<35} {'Return 12m':>12} {'Prob':>8} {'Conf':<10}")
        print("-" * 80)
        for r in results:
            title = (r.title or "")[:33]
            ret = f"{r.predicted_return_12m:>11.1%}" if r.predicted_return_12m is not None else "N/A"
            prob = f"{r.predicted_profitable_12m:>7.1%}" if r.predicted_profitable_12m is not None else "N/A"
            print(f"{r.set_number:<12} {title:<35} {ret:>12} {prob:>8} {r.confidence:<10}")
    finally:
        conn.close()


def _cmd_evaluate() -> None:
    """Show model run history."""
    from db.connection import get_connection

    conn = get_connection()
    try:
        runs = conn.execute("""
            SELECT model_name, horizon_months, task, r_squared, roc_auc,
                   hit_rate, quintile_spread, n_train, n_test, feature_count,
                   trained_at
            FROM ml_model_runs
            ORDER BY trained_at DESC
            LIMIT 20
        """).df()

        if runs.empty:
            print("No model runs found. Run 'train' first.")
            return

        print(f"\nLatest model runs ({len(runs)}):")
        print(runs.to_string(index=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
