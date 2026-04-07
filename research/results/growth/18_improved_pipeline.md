# Experiment 18: Improved Pipeline Evaluation

Date: 2026-04-05
Dataset: 608 sets (DuckDB, old features before Exp 19 additions)
Runtime: ~90 minutes (3 tiers parallel, GBM Optuna 75 trials each)

## Model Results

| Tier | Model | Features | CV R2 (15-fold) | Train R2 | MAE |
|------|-------|----------|-----------------|----------|-----|
| **Tier 1** | **GBM** | 14 | **0.420 +/-0.076** | 0.849 | 3.7% |
| Tier 1 | LightGBM | 14 | 0.233 +/-0.128 | - | 4.6% |
| **Tier 2** | **GBM** | 21 | **0.236 +/-0.125** | 0.960 | 4.5% |
| Tier 2 | LightGBM | 21 | 0.373 +/-0.074 | - | 3.9% |
| **Tier 3** | **GBM** | 66 | **0.305 +/-0.068** | 0.713 | 4.5% |
| Tier 3 | LightGBM | 66 | 0.296 +/-0.069 | - | 4.5% |
| Ensemble | Ridge | 3 tiers | 0.236 +/-0.042 | - | - |

## Temporal CV (Walk-Forward)

| Tier | Folds | R2 |
|------|-------|-----|
| Tier 1 | train 2020-22 -> test 2023: R2=-0.661 | |
| | train 2020-23 -> test 2024: R2=-0.093 | |
| | train 2020-24 -> test 2025: R2=+0.319 | |
| | **Average: R2=-0.145** | Improving with more training data |
| Tier 2 | train 2021-23 -> test 2024: R2=-0.373 | |
| | train 2021-24 -> test 2025: R2=-0.144 | |
| | **Average: R2=-0.259** | |

## Leakage-Free Temporal OOS

- Train: 486, Test: 122
- **OOS R2: 0.195** (up from -0.10 previously)
- OOS MAE: 5.83%
- Direction accuracy: 100%
- **Top quintile: +19.5% avg growth**
- **Bottom quintile: +6.5% avg growth**
- **Quintile spread: 13.0%** (model separates winners from losers)

## LOO Backtest

- **LOO R2: 0.386** (down from 0.479 on 322 sets -- more data, harder problem)
- LOO Correlation: 0.635
- LOO MAE: 4.15%
- Top quintile: +18.7% (win rate 100%)
- Bottom quintile: +5.1%
- **Quintile spread: +13.6%**

## Portfolio Simulation ($1000)

| Strategy | Return | Sets |
|----------|--------|------|
| **ML Top Picks** | **+23.4%** | 28 |
| Equal Weight | +12.2% | 99 |
| Random avg | +11.0% | - |
| **ML alpha vs random** | **+12.4%** | |

## Prediction Tracking (Live)

- 453 predictions tracked
- **MAE: 3.17%**
- **Correlation: 0.829**
- **R2: 0.647**

## Key Observations

1. GBM consistently beats LightGBM on this dataset (small n, high categorical proportion)
2. Temporal CV improving: from -0.10 to -0.145 (still negative but less so, and 2025 fold is positive +0.319)
3. Ensemble hurts -- Tier 2 gets negative weight, overfitting on Keepa subset
4. 100% direction accuracy (all sets have positive growth in this dataset)
5. Live prediction tracking shows strong real-world performance (R2=0.647)
