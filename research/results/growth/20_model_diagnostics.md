# Experiment 20: Model Diagnostics

Date: 2026-04-05
Dataset: 612 sets, 19 features (after MI + redundancy selection)
Model: LightGBM (for diagnostic speed)

## 1. Learning Curve

| n_train | CV R2 | Train R2 | Gap |
|---------|-------|----------|-----|
| 50 | -0.159 | 0.076 | 0.235 |
| 100 | 0.049 | 0.223 | 0.174 |
| 200 | 0.096 | 0.344 | 0.248 |
| 300 | 0.122 | 0.389 | 0.267 |
| 400 | 0.141 | 0.427 | 0.286 |
| 500 | 0.135 | 0.420 | 0.285 |
| 612 | 0.155 | 0.457 | 0.301 |

**Conclusion**: Curve still climbing. More data will help. Target 800-1000 sets.

## 2. Permutation Importance (top 10)

| Feature | Importance | New? |
|---------|-----------|------|
| subtheme_loo | 0.223 | |
| theme_bayes | 0.136 | |
| price_per_part | 0.075 | |
| **currency_cv** | **0.059** | NEW |
| **usd_vs_mean** | **0.054** | NEW |
| **theme_growth_std** | **0.042** | NEW |
| **review_rank_in_retire_year** | **0.036** | NEW |
| **theme_x_price** | **0.036** | NEW interaction |
| log_parts | 0.026 | |
| mfigs | 0.024 | |

## 3. LOFO Importance

Baseline R2 = 0.1774. Features that HURT when present (negative R2 drop):

| Feature | R2 drop | Verdict |
|---------|---------|---------|
| currency_cv | -0.012 | Hurts in combination |
| usd_vs_mean | -0.010 | Hurts in combination |
| rating_value | -0.009 | Hurts in combination |
| rating_x_price | -0.009 | Hurts in combination |
| theme_x_price | -0.005 | Marginal |

**Action**: Added LOFO pruning step to feature selection pipeline.

## 4. Residual Analysis

- Mean residual: +1.50% (systematic underprediction)
- Bottom quintile (0-5% actual): residual = -3.96% (overpredicts losers)
- Top quintile (17-35% actual): residual = +12.48% (underpredicts winners)

**Model compresses predictions toward the mean.**

## 5. Calibration by Decile

Every decile has negative bias (-0.1% to -3.4%). Worst at the top:
- Predicted 13-17% -> Actual 17.6% (bias = -3.4%)
- Predicted 12-13% -> Actual 15.5% (bias = -2.8%)

**Action**: Added isotonic calibration to training pipeline.

## 6. Overfit Summary

- Train R2: 0.457
- CV R2: 0.177
- Gap: 0.280 (WARNING)
- CV fold variance: 0.057 (OK)
- Samples/feature: 32

**Actions taken**:
- Early stopping (30 rounds patience) for LightGBM/CatBoost
- LOFO pruning in feature selection
- Isotonic calibration for bias correction
- Prediction clipping [0%, 50%]
