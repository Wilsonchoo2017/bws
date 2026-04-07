# Research Findings: LEGO Set Investment Return Prediction

21 experiments across EDA, feature engineering, model tuning, portfolio optimization, and model architecture.

## Current Model (707 sets, hurdle architecture)

**Two-stage hurdle model** (LightGBM):
1. **Classifier**: P(avoid) — trained on ALL sets, identifies losers (growth < 5%)
2. **Regressor**: E[growth | non-loser] — trained on winners only, predicts upside
3. **Combined**: P(good) * regressor + P(bad) * median_loser_return

**Tier 1** (intrinsic features): 13 features after LOFO selection from 30 candidates
- Top features: subtheme_loo, theme_bayes, price_per_part, theme_growth_std
- Target winsorization (P5/P95), monotonic constraints, recency-weighted samples
- Yeo-Johnson target transform, Huber loss, early stopping

**Preprocessing improvements**:
- Target winsorization at P5/P95 (reduces outlier pull on mean compression)
- Monotonic constraints: mfigs+, rating+, reviews+, licensed+, mfig_value+
- Recency weighting: half-life=3yr exponential decay (newer cohorts matter more)
- Isotonic calibration: fixed scale bug (wrapper ensures raw-scale CV predictions)

## Key Insights

1. **Theme identity is king** -- subtheme + theme explain ~75% of feature importance
2. **More data > more features** -- R2 improved from 0.27 (157 sets) to 0.48 (322 sets) with same features
3. **Hurdle model fixes mean compression** -- regressor no longer wastes capacity on losers
4. **Google Trends is dead** -- anti-signal confirmed across 7 methods, scraping disabled
5. **LEGO base win rate is 80%+** -- ML value is in ranking (which sets), not direction
6. **BrickLink monthly sales are leaky** -- all post-retirement (2025+), need pre-retirement scraping
7. **usd_vs_mean** -- 3rd strongest non-leaky feature (r=-0.231), sets priced above global avg grow less
8. **Overfitting gap** -- addressed via monotonic constraints, LOFO pruning, early stopping, recency weighting

## Production Files

| File | Purpose |
|------|---------|
| `services/ml/growth/training.py` | Hurdle model training (classifier + regressor) |
| `services/ml/growth/classifier.py` | Avoid classifier (P(loser) gate) |
| `services/ml/growth/prediction.py` | Hurdle-combined predictions |
| `services/ml/growth/model_selection.py` | LightGBM tuning, monotonic constraints, CV |
| `services/ml/growth/features.py` | Feature engineering (30 Tier 1 candidates) |
| `services/ml/growth/feature_selection.py` | MI + redundancy + LOFO pruning |
| `services/ml/growth/calibration.py` | Isotonic calibration |
| `services/ml/growth/conformal.py` | Conformal prediction intervals |
| `services/ml/growth/persistence.py` | Model save/load (joblib) |
| `services/ml/buy_signal.py` | Buy signal calculator (MYR) |
| `services/ml/portfolio_optimizer.py` | Mean-variance knapsack (MYR) |
| `services/ml/pg_queries.py` | PostgreSQL data access |
| `services/scoring/growth_provider.py` | Scoring provider (loads pre-trained) |

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /ml/growth/predictions` | All ML growth predictions |
| `GET /ml/growth/predictions/{set_number}` | Single set prediction |
| `GET /ml/buy-signal/{set_number}?discount=20` | Buy signal with scenarios |
| `GET /ml/portfolio?budget=3000&risk=balanced` | MYR portfolio optimizer |
| `GET /ml/kelly?budget=X&max_positions=N` | Kelly position sizing |
| `POST /ml/growth/retrain` | Force retrain |

## Experiment Log

| # | Topic | n | Best Result | Key Finding |
|---|-------|---|-------------|-------------|
| 01 | EDA (38 sets) | 38 | - | keepa_discount_pct r=-0.58 (later found leaky) |
| 02 | Expanded (211 sets) | 211 | AUC 0.857 | value_to_rrp dominant (leaky) |
| 03 | No-leakage model | 211 | AUC 0.748 | BrickLink features also leaky |
| 04 | Temporal (candlestick) | 48 | R2 0.248 | Early momentum predicts returns |
| 05 | Intrinsics only | 266 | AUC 0.767 | Theme is #1 predictor, zero leakage |
| 06 | + Keepa | 113 | R2 0.511 | keepa_discount_pct leaky (3P markup) |
| 07 | Keepa timeline | 80 | R2 0.285 | bb_premium at OOS is real signal |
| 08 | Combined feature sets | 157 | R2 0.444 | Subtheme features help with more data |
| 09 | Enriched intrinsics | 157 | R2 0.432 | Added features hurt (overfitting) |
| 10 | Sales + subtheme | 157 | R2 0.429 | Sales features leaky |
| 11 | HP tuning | 185 | R2 0.401 | d=4 leaf=6 is optimal (+0.14 R2) |
| 12 | Bayesian theme | 214 | R2 0.337 | Bayesian smoothing helps small themes |
| 13 | ML Kelly | 223 | - | LEGO base rate too high for classic Kelly |
| 14 | Portfolio optimizer | 223 | Sharpe 6.94 | Mean-variance knapsack with integer constraints |
| 15 | Backtest | 41 | +23.8% | Optimizer beats equal-weight at small budgets |
| 16 | GT deep dive | 78 | - | GT is anti-signal (6 methods confirm) |
| 17 | Theme GT collection | - | - | Enqueued theme-level GT; only 24 snapshots |
| 18 | Improved pipeline | 608 | OOS R2 0.195 | Huber, Yeo-Johnson, temporal CV, conformal, SHAP |
| 19 | Feature exploration | 684 | usd_vs_mean r=-0.231 | Best new feature: USD price vs global avg |
| 19b | GT/sleeper/currency | 706 | GT confirmed dead | usd_vs_mean added; GT scraping disabled |
| 19c | BrickLink sales | 349 | All post-retirement | Leaky — all sales are post-retirement (2025+) |
| 20 | Model diagnostics | 612 | gap=0.28 | LOFO pruning, isotonic cal, learning curve |
| 21 | Hurdle model | 707 | - | Two-stage: classifier gates regressor |

## Architecture Change: v1 -> v2

**v1** (single regressor): Train GBM/LightGBM on ALL sets, predict growth %.
- Problem: model compresses toward mean, underpredicts winners by 12%, overpredicts losers by 4%.

**v2** (hurdle model): Classifier + regressor on non-losers.
- Classifier catches bad sets (optimized for recall on losers)
- Regressor focuses on ranking winners (cleaner training signal)
- Combined via: P(good) * E[growth|good] + P(bad) * median_loser
- Also adds: target winsorization, monotonic constraints, recency weighting

## DuckDB Deprecation

All active ML pipeline code now uses PostgreSQL exclusively:
- `services/ml/pg_queries.py` — data access
- `./train` — offline training script (PG only)
- Old DuckDB code in `services/ml/queries.py`, `services/ml/training.py`, etc. is deprecated

## Next Steps

1. **Run training** with new hurdle model and compare metrics
2. **Pre-retirement BL sales** — scrape monthly sales for active sets
3. **More data** — learning curve still climbing at 700 sets, target 1000+
4. **Quantile regression** — P10/P50/P90 for proper uncertainty
5. **Live tracking feedback loop** — use prediction vs actual to recalibrate
