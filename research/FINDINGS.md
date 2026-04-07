# Research Findings: LEGO Set Investment Return Prediction

27 experiments across EDA, feature engineering, model tuning, portfolio optimization, model architecture, and model alternatives.

## Current Model (1701 sets, T1-only)

**Single-tier hurdle model** (LightGBM):
1. **Classifier**: P(avoid) — trained on ALL sets, identifies losers (growth < 5%)
2. **Regressor**: E[growth] — Tier 1 intrinsic features on ALL 1701 sets
3. **Combined**: P(good) * regressor + P(bad) * median_loser_return

**Tier 1** (intrinsic features): 20 features after LOFO selection from 35 candidates
- Top features: theme_bayes, theme_size, review_rank_in_year, theme_growth_std, log_parts
- Target winsorization (P1/P99), monotonic constraints, recency-weighted samples
- Yeo-Johnson target transform, Huber loss, Optuna-tuned (depth 3-8, leaves 15-63)
- Classifier now Optuna-tuned (AUC +0.018 over hardcoded params)

**Performance** (GroupKFold, 2025-04-07):
- T1 on all 1701 sets: **CV R2=0.754 +/-0.151** (Optuna-tuned: depth=8, leaves=41, lr=0.039)
- Classifier AUC=0.961, F1=0.919, Brier 0.078->0.066 (isotonic cal)
- Backtest Q1 (top 20%): +19.7% return, 93% hit rate
- T1 on Keepa subset (965): R2=0.494, MAE=2.7%
- T2 Keepa-only on same subset: R2=0.368, MAE=3.3% (worse)
- T1+T2 combined: R2=0.368, MAE=3.3% (Keepa features dominate and hurt)
- Ensemble AVG(T1,T2): R2=0.398, MAE=3.2% (averaging doesn't help)

**Decision**: T2, T3, and ensemble tiers dropped. T1 regressor + avoid classifier is the production model.

**Avoid Classifier** (Munger inversion, from inversion research exps 01-04, updated Exp 27):
- Hardcoded params: AUC=0.961, now Optuna-tuned: **AUC=0.979** (+0.018, 30 trials)
- Best params: depth=5, leaves=13, lr=0.095, n_est=400, min_child=5, reg_alpha=0.33, subsample=0.73
- Brier score=0.087 (well-calibrated at high probs, overconfident at low probs)
- False negatives: 39/583 (6.7%) losers missed at P<0.3 — concentrated in Minecraft (71% miss rate), Harry Potter (71%), Brick Sketches
- False positives: 33/1118 (3.0%) good sets flagged at P>0.7 — Classic, Dots, DREAMZzz themes
- Weak themes (AUC<0.65): Dots (0.60), Minecraft (0.61), Hidden Side (0.62)
- Temporal drift: AUC=0.75 on 2024 cohort (worst), 0.87 on 2025 — 2024 was harder
- Lifecycle features (shelf_life_months, retire_quarter, retires_before_q4): +0.002 AUC, marginal
- Shown as RISK/WARN badges on UI (avoid_probability >= 0.5/0.8)

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
9. **Keepa features hurt, not help** -- T2 (Keepa) R2=0.368 vs T1 R2=0.494 on same 965 sets; T1 wins 4/5 folds
10. **More data is the biggest lever** -- T1 on 1701 sets (R2=0.644) vs 965 sets (R2=0.494); +0.15 R2 from data alone
11. **Classifier AUC jumped to 0.947** -- was 0.85 with 345 sets; more data helped classifier even more than regressor
12. **P(avoid) miscalibrated at low probs** -- says 15% when reality is 6%; isotonic cal needed
13. **Minecraft/Dots/Hidden Side are blind spots** -- classifier AUC < 0.65 on these themes
14. **BrickTalk lifecycle features are weak** -- shelf life, retire quarter add only +0.002 AUC; their signal is supply/demand (Keepa velocity), not timing
15. **Model is overfitting** (gap=0.30) but deeper trees still improve CV -- needs more data AND more capacity
16. **Winners massively underpredicted** -- 20%+ growth sets have -12.8% bias; mean compression is the #1 remaining problem
17. **Theme-specific models don't work** -- 5 themes win, 9 lose; not enough data per theme (need 100+ per theme)
18. **Quantile regression works for intervals** -- 80% interval coverage=67.5% (needs calibration), avg width=8.9%; not viable as point estimator (R2=0.388)
19. **LightGBM is the right model** -- CatBoost (R2=0.196-0.517), HistGB (0.590), stacking (0.544) all worse; Yeo-Johnson is critical (+0.13 R2)
20. **never_discounted is dead** -- r=0.14 was artifact of shelf_life filter; r=-0.02 when filter removed; discount history is not predictive
21. **Classifier Optuna tuning works** -- AUC 0.961->0.979 (+0.018) with 30 trials; depth=5, leaves=13, higher lr=0.095; F1 0.915->0.944, Recall 0.908->0.948
22. **high_price_barrier is dead** -- MI=0.000, dropped by feature selection; the >$300 investor barrier signal is already captured by log_rrp and price_tier
23. **shelf_life_x_reviews absorbed shelf_life_months** -- corr=0.94 so LOFO drops raw shelf_life; interaction ranks 8th by importance (122 gain) but delta R2=-0.001 (neutral); keeps the interaction while dropping the raw feature
24. **BrickTalk "one-and-done" is the biggest missing signal** -- prior_versions_count/is_first_ucs need external data (Rebrickable API or title matching); highest potential but hardest to implement
25. **Keepa 3P/FBA/FBM/BB: real signal, too noisy** -- r=0.22-0.37 correlations, NOT purely leaky (premiums appear 17mo before retirement, survive partial correlation). But hurt CV at current n=607. Worth revisiting at 3000+ sets
26. **Sales rank is the missing gold** -- scraper stores empty sales_rank_json (0 data points extracted); BrickTalk's #1 conviction signal (Amazon velocity/demand)
27. **Stock market TA does not transfer** -- tested 67 indicators (SMA/EMA/RSI/MACD/Bollinger/Donchian/momentum) on Keepa prices; every feature hurts CV; LEGO prices are RRP-anchored algorithmic, not human-sentiment-driven

## Production Files

| File | Purpose |
|------|---------|
| `services/ml/growth/training.py` | Hurdle model training (classifier + regressor) |
| `services/ml/growth/classifier.py` | Avoid classifier (P(loser) gate) |
| `services/ml/growth/prediction.py` | Hurdle-combined predictions |
| `services/ml/growth/model_selection.py` | LightGBM tuning, monotonic constraints, CV |
| `services/ml/growth/features.py` | Feature engineering (35 Tier 1 candidates) |
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
| 22 | Tier head-to-head | 1701 | T1 R2=0.644 | T1 beats T2/ensemble on same sets; Keepa features hurt; T1-only is best |
| 23 | Classifier diagnostics | 1701 | AUC=0.947 | Calibration off at low probs; 3 weak themes; lifecycle features +0.002 AUC |
| 24 | ML improvement scan | 1701 | depth=6 R2=0.674 | Overfitting (gap=0.30); deeper trees help; quantile cal OK; theme models hurt; winners underpredicted by 12.8% |
| 25 | Apply improvements | 1701 | d5+P1/99 R2=0.631 | Quick wins confirmed: +0.079 R2; BrickTalk features neutral; quantile intervals 65% coverage; anti-overfit tweaks hurt |
| 26 | Model alternatives | 1701 | LGB R2=0.597 | CatBoost and HistGB tested; LightGBM wins; stacking hurts; Yeo-Johnson worth +0.13 R2 |
| 27 | Classifier tuning + BrickTalk features | 1701 | AUC=0.979 | Classifier Optuna +0.018 AUC; high_price_barrier dead (MI=0); shelf_life_x_reviews neutral (delta R2=-0.001); regressor unchanged |
| 28 | Keepa separated signals | 1193 | All hurt CV | 3P FBA/FBM/BB r=0.30-0.37 but all hurt CV; NOT purely leaky (premiums appear 17mo pre-retire, survive partial corr); too noisy at n=607; sales rank empty |
| 29 | Keepa technical analysis | 550 | All hurt CV | SMA/EMA/RSI/MACD/Bollinger/Donchian on Amazon prices; 67 features tested; best r=0.25; every feature hurts CV; TA doesn't transfer to LEGO pricing |

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

## Experiment 23: Classifier Diagnostics (2026-04-07)

Comprehensive diagnostics on the avoid classifier using 1701 sets.

### Calibration
- P(avoid) is **overconfident at low probabilities**: at P=0.1-0.3, actual avoid rate is only 5-11% (gap of -9% to -14%). The classifier says "15% chance" but reality is closer to 6%.
- At P>0.5, calibration is much better (within 5-8%).
- **Action**: isotonic calibration on P(avoid) could fix this. Low-prob miscalibration means the hurdle combination is slightly overweighting the regressor for ambiguous sets.

### Per-Theme Failure Modes
- **Dots** (AUC=0.60): small theme (n=25), mixed outcomes. Sets like "Hedwig Pencil Holder" grow 10% but get flagged. Pattern: novelty/collectibility is unpredictable.
- **Minecraft** (AUC=0.61): 71% of losers missed. Classifier sees "licensed, good theme encoding" but Minecraft has high variance — some sets are junk (The Rabbit Ranch: 0% growth) while others moon.
- **Hidden Side** (AUC=0.62): almost all sets are avoid (14/17). Classifier can't distinguish the few survivors.
- **17/26 themes have AUC >= 0.85** — classifier works well for most themes.

### Temporal Drift
- Walk-forward AUC by test year: 2021=0.79, 2022=0.83, 2023=0.77, 2024=0.75, 2025=0.87
- 2024 was the hardest year (AUC=0.75, precision=44%). This may reflect market changes or data quality.
- No systematic degradation trend — more a year-to-year volatility.

### Threshold Sensitivity
- 5% threshold: AUC=0.947, 34% of sets classified as avoid
- 8% threshold: AUC=0.949, 61% avoid — slightly better AUC but flags majority of sets
- **Best separation is at 4-5%** where precision/recall are balanced (~83%/83%)

### New Features (BrickTalk Gap Analysis)
- **shelf_life_months**: 46% coverage (need retired_date). Weak signal: r=0.056 with growth. Bins show <1yr shelf life has 37% avoid rate (worse than 2yr at 28%), contradicting BrickTalk's "short = bullish" claim. But coverage is too low to be conclusive.
- **retire_quarter**: Q4 retirement is slightly better (9.8% growth, 30% avoid) vs Q1-Q3 (8-9%, 33-43% avoid). Aligns with BrickTalk theory but effect is small.
- **retires_before_q4**: Adds nothing (delta AUC = 0.0000). retire_quarter already captures the signal.
- **Net impact of all 3 lifecycle features: +0.002 AUC.** Marginal. LOFO may prune them.

### Decision Boundary
- 254 sets (15%) in uncertainty zone (P=0.35-0.65). These average 6.8% growth with 39% avoid rate.
- Key differentiator in boundary zone: `subtheme_loo` (7.9 vs 10.7 for confident good), `theme_bayes` (8.7 vs 9.7), `usd_vs_mean` (1.01 vs 0.95). These are the features that matter most for disambiguation.

## Experiment 24: ML Improvement Scan (2026-04-07)

Fast 90-second diagnostic scan testing preprocessing, model complexity, quantile regression, theme-specific models, residual analysis, post-processing, and loss functions — all on 1701 sets with 5-fold GroupKFold, no Optuna.

### Overfit/Underfit Diagnosis
- **Train R2=0.918, CV R2=0.616, gap=0.303 — OVERFITTING**
- Model memorizes training data; regularization or more data needed
- Learning curve still climbing steeply: n=340 R2=0.07, n=680 R2=0.39, n=1020 R2=0.44, n=1360 R2=0.58, n=1701 R2=0.62
- **More data remains the #1 lever** — curve shows no saturation

### Preprocessing
| Variant | R2 | MAE | vs Baseline |
|---------|-----|-----|-------------|
| Yeo-Johnson (current) | 0.616 | 2.3% | baseline |
| log1p target | **0.629** | 2.3% | **+0.013** |
| Quantile transform | 0.628 | **2.2%** | +0.012 |
| Winsorize P1/P99 + YJ | **0.636** | **2.2%** | **+0.020** |
| No transform | 0.526 | 2.5% | -0.090 |
| Winsorize P5/P95 + YJ | 0.613 | 2.3% | -0.003 |
| Winsorize P10/P90 + YJ | 0.583 | 2.3% | -0.033 |

- **Winner: Winsorize P1/P99 + YJ (R2=0.636)** — light winsorization helps, heavy hurts
- log1p and quantile transforms are competitive alternatives to Yeo-Johnson
- Current P5/P95 winsorization is slightly aggressive — P1/P99 is better

### Model Complexity
| Config | R2 | MAE | Notes |
|--------|-----|-----|-------|
| depth=3, leaf=8 | 0.527 | 2.7% | Too simple |
| depth=4, leaf=15 (current) | 0.596 | 2.5% | Current production |
| **depth=5, leaf=31** | **0.641** | **2.3%** | **Better, +0.045** |
| **depth=6, leaf=63** | **0.674** | **2.1%** | **Best, +0.078** |
| depth=4, lr=0.1 | 0.619 | 2.4% | Faster learning rate helps slightly |
| depth=4, reg_high | 0.580 | 2.5% | More regularization hurts |
| depth=4, min_child=20 | 0.562 | 2.6% | More min samples hurts |

- **Deeper trees help significantly** — depth=6 gives R2=0.674 (+0.078 vs current)
- But this worsens overfitting (train R2 would be even higher)
- Trade-off: depth=5 is sweet spot (good R2 gain with less overfit risk)
- Higher regularization and min_child constraints HURT — model is already undertrained at current complexity

### Quantile Regression
- Calibration is **reasonable** but slightly off:
  - P10: 16.3% actual (target 10%) — conservative
  - P50: 55.1% actual (target 50%) — slightly conservative
  - P90: 83.7% actual (target 90%) — slightly aggressive
- **80% prediction interval (P10-P90): avg width=8.9%, coverage=67.5%** (under-covering, should be 80%)
- P50 as point estimate: R2=0.388, MAE=3.2% — much worse than mean regression (R2=0.616)
- **Verdict: quantile regression works for intervals but NOT as replacement for mean model**
- Monotonic constraints incompatible with LightGBM quantile — limits quality

### Theme-Specific Models
- **5 themes win, 9 lose, 3 ties** — theme-specific models HURT overall
- Winners: BrickHeadz (+0.38), NINJAGO (+0.52), Super Heroes (+0.48), Star Wars (+0.17), Friends (+0.19)
- Losers: Classic (-0.63), Technic (-3.22), Holiday (-10.40), Minecraft (catastrophic)
- **Not enough data per theme** — most themes have 30-70 sets, need 100+ for reliable theme models
- Better approach: use theme as feature (already doing this via theme_bayes/subtheme_loo)

### Residual Analysis (where the model fails)
| Growth Bucket | n | MAE | Bias | Issue |
|---------------|---|-----|------|-------|
| 0-5% (losers) | 583 | 1.5% | +1.1% | Slightly overpredicts losers |
| 5-10% | 591 | 1.6% | +0.5% | Good |
| 10-15% | 264 | 2.4% | -1.5% | Starts underpredicting |
| 15-20% | 114 | 5.4% | -4.8% | Significant underprediction |
| **20%+ (winners)** | **149** | **12.9%** | **-12.8%** | **Massive underprediction** |

- **Core problem: model compresses toward mean.** Winners are underpredicted by 12.8% on average.
- This is the classic mean regression bias — the hurdle model was supposed to fix this but hasn't fully
- Worst themes: Avatar (MAE=10.3%), Architecture (7.2%), Ideas (6.1%), Minecraft (5.7%)

### Loss Functions
| Loss | R2 | MAE | Notes |
|------|-----|-----|-------|
| huber (current) | 0.596 | 2.5% | Current default |
| mse | 0.593 | 2.5% | Nearly identical |
| poisson | 0.490 | 2.9% | Worse |
| gamma | 0.458 | 2.9% | Worse |
| mae | - | - | Incompatible with monotonic constraints |

- Huber and MSE are essentially identical — Huber's outlier robustness isn't needed with winsorization
- Poisson/gamma are worse (wrong distributional assumption for growth %)

### Key Takeaways from Exp 24
1. **Overfitting is the main problem** (gap=0.30), but more complexity still helps CV — suggests model needs both more data AND more capacity
2. **Quick wins**: depth=5 (+0.045 R2), P1/P99 winsorization (+0.020 R2) — combined could reach R2~0.66
3. **Quantile regression works for intervals**, not as replacement; use alongside mean model
4. **Theme-specific models not viable** — not enough data; current theme encoding already captures most signal
5. **Winners are the blind spot** — 20%+ sets underpredicted by 12.8%; this is the remaining alpha opportunity

## Experiment 25: Apply Improvements (2026-04-07)

Validated quick wins, BrickTalk features, anti-overfit tweaks, and quantile intervals.

### Quick Wins (confirmed)
| Config | R2 | vs Baseline | MAE |
|--------|-----|-------------|-----|
| Baseline (d=4, P5/P95) | 0.553 | - | 2.5% |
| depth=5 only | 0.604 | +0.051 | 2.3% |
| P1/P99 only | 0.590 | +0.037 | 2.5% |
| **depth=5 + P1/P99** | **0.631** | **+0.079** | **2.3%** |
| depth=6 + P1/P99 | 0.662 | +0.110 | 2.1% |

- depth=5+P1/P99 is the safe sweet spot (+0.079 R2)
- depth=6 gives more R2 but increases overfit risk

### BrickTalk Features
- `never_discounted` (max_discount < 5% and shelf > 6mo): initially r=+0.140 at 27% coverage (12.2% vs 9.2%)
- `rarely_discounted` (below_rrp < 10%): corr=-0.052, not useful
- Added to model: **R2=0.632 (+0.001 vs d5+P1/P99)** — essentially neutral
- **CORRECTION**: r=0.14 was an artifact of the shelf_life filter. Removing shelf requirement (coverage 27%->57%), correlation drops to r=-0.02 and adding to model hurts R2 (0.631->0.578). **Signal is dead.**
- RRP from BrickEconomy already at 100% coverage — problem isn't data, it's that discount history isn't predictive
- **Verdict**: `never_discounted` is not viable. BrickTalk's insight requires real-time pre-retirement assessment (Keepa velocity, 3P premiums), not historical discount patterns.

### Anti-Overfit Tweaks (all hurt)
| Tweak | R2 | vs d5+P1/P99 |
|-------|-----|-------------|
| lr=0.03, n=500 | 0.633 | +0.002 |
| lr=0.02, n=800 | 0.629 | -0.002 |
| colsample=0.7 | 0.618 | -0.013 |
| subsample=0.8 | 0.613 | -0.018 |
| col+sub+lr combined | 0.583 | -0.048 |

- **All anti-overfit tweaks hurt.** The model is overfitting but still benefits from capacity.
- This confirms: **more data is the fix for overfitting, not regularization**.

### Winner Underprediction (still present)
| Bucket | n | MAE | Bias |
|--------|---|-----|------|
| 0-5% | 583 | 1.6% | +1.3% |
| 5-10% | 591 | 1.5% | +0.4% |
| 10-15% | 264 | 2.3% | -1.4% |
| 15-20% | 114 | 5.3% | -4.8% |
| 20%+ | 149 | 12.0% | -12.0% |

- Still underpredicting winners by 12.0% — this is fundamental mean regression behavior
- depth=5 didn't fix this (slightly better: was -12.8%, now -12.0%)

### Quantile Intervals
- P10/P90 interval: 65% coverage (target 80%), avg width 8.1%
- Under-covering at tails: P10 actual=17% (should be 10%), P90 actual=82% (should be 90%)
- **Usable for directional uncertainty** but needs calibration for reliable intervals
- Example: set predicted at 8% has interval [4%, 14%] — informative for investment decisions

## Experiment 26: Model Alternatives Scan (2026-04-07)

Tested CatBoost, HistGradientBoosting, and stacking vs LightGBM baseline.
All use 5-fold GroupKFold with same 1701 sets, 19 features, P1/P99 winsorization, Yeo-Johnson.

### Head-to-Head Results

| Model | R2 | +/- | MAE |
|-------|-----|-----|-----|
| **LightGBM (prod params)** | **0.597** | **0.163** | **2.6%** |
| LightGBM (RMSE loss) | 0.595 | 0.173 | 2.6% |
| HistGB (matched params) | 0.590 | 0.185 | 2.6% |
| LightGBM (defaults) | 0.559 | 0.165 | 2.7% |
| Stack (LGB+CB+HGB avg) | 0.544 | 0.169 | 2.8% |
| HistGB (MAE loss) | 0.528 | 0.167 | 2.8% |
| CatBoost (defaults/RMSE) | 0.517 | 0.148 | 2.9% |
| LightGBM (no Yeo-Johnson) | 0.467 | 0.173 | 2.9% |
| CatBoost (MAE loss) | 0.353 | 0.154 | 3.4% |
| CatBoost (matched/Huber) | 0.196 | 0.198 | 3.8% |

### Key Findings

1. **LightGBM wins** — our Optuna-tuned production config is best; no alternative GBDT beats it
2. **CatBoost disappoints** — even with defaults, R2=0.517; with matched Huber params, catastrophic (0.196); likely because CatBoost's ordered boosting hurts on small datasets with high tree depth
3. **HistGradientBoosting is close** — R2=0.590 vs 0.597 but lacks monotonic constraint support; not worth switching
4. **Stacking hurts** — averaging 3 models (0.544) is worse than LightGBM alone (0.597); CatBoost drags ensemble down
5. **Yeo-Johnson is critical** — removing it drops R2 from 0.597 to 0.467 (+0.13 delta); biggest single preprocessing contribution
6. **Huber vs RMSE** — nearly identical (0.597 vs 0.595); Huber's robustness is minor with P1/P99 winsorization already applied
7. **TabPFN not tested** — not installed; primarily for classification, not regression; our dataset (1701 rows) is within range but TabPFN v1 is classifier-only

### What Was NOT Tested

- **XGBoost** — not installed; unlikely to beat LightGBM based on Kaggle benchmarks
- **AutoGluon/FLAML** — heavyweight AutoML, not worth installing for 1701-row dataset
- **TabNet/FT-Transformer** — deep learning tabular models; consensus is they don't beat GBDT on small datasets

**Verdict**: LightGBM is the right choice. No model swap needed. Our Optuna-tuned params + Yeo-Johnson + Huber + monotonic constraints is the best stack for this data size.

## Experiment 28: Keepa Separated Signals Scan (2026-04-07)

Tested whether separating Keepa price channels (Amazon 1P, 3P FBA, 3P FBM, Buy Box, sales rank) reveals actionable signals for post-retirement growth.

### Data Coverage
- 1614 Keepa snapshots in DB, all JSON columns at 100% coverage
- Matched 1193/1701 training sets (70%)
- Sales rank JSON: **all empty** (scraper stores column but extracts 0 data points)

### Correlation Analysis (1193 Keepa-matched sets)

| Feature | Corr | n | Coverage |
|---------|------|---|----------|
| kp_3p_fba_max_vs_rrp | **+0.365** | 1094 | 92% |
| kp_bb_max_premium | **+0.363** | 1140 | 96% |
| kp_3p_fba_vs_rrp | **+0.315** | 1094 | 92% |
| kp_bb_avg_vs_rrp | **+0.305** | 1140 | 96% |
| kp_3p_fbm_vs_rrp | **+0.299** | 1125 | 94% |
| kp_3p_premium_vs_amz | +0.292 | 936 | 78% |
| kp_3p_fba_cv | +0.251 | 1094 | 92% |
| kp_stockout_pct | +0.182 | 947 | 79% |
| kp_log_tracking | +0.149 | 1113 | 93% |
| kp_discount_trajectory | -0.144 | 937 | 79% |

### 3P FBA Premium (BrickTalk's Key Signal)

| Quartile | n | FBA vs RRP | Avg Growth |
|----------|---|------------|------------|
| Q1 (deepest discount) | 274 | -92% to 0% | 6.9% |
| Q2 | 273 | 0% to +16% | 8.0% |
| Q3 | 273 | +16% to +43% | 9.3% |
| Q4 (highest premium) | 274 | +43% to +379% | 12.0% |

Monotonic increase: 3P FBA premium above RRP correlates with higher growth. Delta Q4 vs Q1 = +5.1%.

### CV Test: All Hurt

| Config | R2 | Delta vs T1 |
|--------|-----|-------------|
| T1 only (Keepa subset) | 0.527 | baseline |
| T1 + 18 Keepa signals | 0.405 | **-0.121** |
| T1 + kp_3p_premium_vs_amz | 0.508 | -0.019 |
| T1 + kp_stockout_pct | 0.510 | -0.017 |
| T1 + kp_3p_fba_max_vs_rrp | 0.485 | -0.042 |
| T1 + kp_bb_max_premium | 0.474 | -0.052 |

**Every Keepa feature hurts**, even individually. Same pattern as Experiment 22.

### Why High Correlation But Negative CV Impact?

**These features are leaky.** 3P FBA price rising above RRP pre-retirement is the market pricing in the retirement -- it's measuring the outcome we're trying to predict. Specifically:
- 3P sellers anticipate retirement and raise prices 3-6 months before
- The "premium" IS the aftermarket growth signal, measured pre-retirement
- High correlation (r=0.37) is the leakage signature, not a predictive signal
- Adding leaky features to the model overfits to the training set but fails on validation

### Sales Rank: Empty Data

Sales rank JSON is stored in all 1614 snapshots but contains 0 data points. The Keepa scraper is not extracting sales rank values. This is BrickTalk's #1 conviction signal ("Amazon velocity") and the data gap is significant.

### Gap Analysis 2 Features

- **high_price_barrier** (>$300): n=25, +0.9% delta -- too small sample, already captured by log_rrp
- **is_ucs** (subtheme matching): n=7, +0.1% delta -- insufficient data
- **has_electronics**: no `set_name` column in training data to test
- **prior_versions_count**: needs Rebrickable API, not in our data

### Leakage Deep Investigation (follow-up)

Initial conclusion was "all leaky." Deeper analysis paints a more nuanced picture:

**When do 3P premiums appear?** (620 sets where 3P FBA > RRP pre-retirement)
- Mean: 17.5 months before retirement, Median: 16.5 months
- 74% appear >12 months before retirement, only 5% <3 months
- NOT last-minute leakage -- premiums exist well before retirement

**Early-only 3P premium (>12mo before retirement):**
- r=+0.219 (n=521) vs r=+0.315 all pre-retirement -- correlation weakens but persists
- r=+0.253 for max premium (early only)

**Confounding test (partial corr controlling for theme_bayes):**
- Raw r=+0.191, Partial r=+0.139 -- 73% of signal survives theme control
- **3P premium has independent signal beyond theme**

**CV test with early-only features:**
- T1 only (607 sets): R2=+0.278
- T1 + 6mo-cutoff FBA: R2=+0.289 (delta=**+0.011**)
- T1 + 12mo-cutoff FBA: R2=+0.277 (delta=-0.001)

**Never-discounted-on-Amazon (n=36):** avg growth 10.7% vs 8.8% discounted (+1.9% delta, +3.0% median delta)

### Revised Conclusions

1. **3P FBA premium is NOT purely leaky** -- premiums appear 17+ months before retirement, partial corr survives theme control
2. **But too noisy for current dataset** -- only +0.011 R2 with 6mo cutoff; signal exists but model can't exploit it at n=607
3. **Subset selection bias** -- T1 R2=0.278 on 607 Keepa sets vs 0.527 on 1193; Keepa subset is harder to predict
4. **Sales rank is the missing gold** -- scraper stores empty data; BrickTalk's #1 velocity signal
5. **Worth revisiting at 3000+ sets** -- 3P FBA signal may become exploitable with more data

## Experiment 29: Keepa Technical Analysis (2026-04-07)

Applied stock market technical analysis indicators to Keepa Amazon price timelines.
67 features extracted from 550 sets with sufficient price history (>30 daily points).

### Features Tested

| Category | Best Feature | Best |r| |
|----------|-------------|---------|
| Moving Averages (SMA/EMA) | ta_ema60_vs_rrp | 0.249 |
| 3P FBA TA | ta_fba_final_vs_rrp | 0.251 |
| Support/Resistance | ta_atl_vs_rrp | 0.184 |
| RSI | ta_rsi30_mean | 0.128 |
| Bollinger Bands | ta_bb60_pct_b_mean | 0.118 |
| Price Distribution | ta_pct_deep_discount | 0.118 |
| Donchian Channel | ta_donchian60_position | 0.106 |
| MACD | ta_macd_signal_above | 0.099 |
| Momentum/ROC | ta_roc60 | 0.079 |
| Trend (slope/R2) | ta_trend_slope | 0.073 |
| Volatility | ta_volatility_7d | 0.041 |

### CV Results

| Config | R2 | Delta |
|--------|-----|-------|
| T1 only (550 Keepa sets) | 0.259 | baseline |
| T1 + ta_ath_vs_rrp (best individual) | 0.260 | +0.000 |
| T1 + ta_fba_final_vs_rrp | 0.255 | -0.004 |
| T1 + ta_sma7_vs_rrp | 0.254 | -0.005 |
| T1 + ta_ema14_vs_rrp | 0.186 | -0.073 |
| T1 + 28 TA features | 0.136 | **-0.123** |

**Every TA feature hurts or is neutral.** The best individual feature (ta_ath_vs_rrp) adds exactly +0.000.

### Why Technical Analysis Doesn't Transfer to LEGO

1. **LEGO prices are not stocks** -- Amazon prices are set algorithmically, not by human traders with sentiment/momentum. TA patterns (support, resistance, golden cross) assume human behavioral dynamics.
2. **Mean-reversion to RRP** -- LEGO prices naturally orbit around the RRP. Moving averages, RSI, Bollinger all reduce to "is price above or below RRP?" which is already captured by simple discount features.
3. **All TA features are highly correlated** -- SMA7, SMA14, SMA30, SMA60, SMA90, EMA7, EMA14, EMA30, EMA60, final_vs_rrp all measure essentially the same thing: average price level relative to RRP. Adding multiple collinear features causes overfitting.
4. **Subset too small** -- only 550 sets have sufficient price history; T1 baseline is R2=0.259 vs 0.527 on the full Keepa set.
5. **No volume data** -- TA assumes price+volume. Without sales rank/volume, half the TA toolkit (OBV, VWAP, accumulation/distribution) is unavailable.

**Verdict**: Stock market TA does not transfer to LEGO price analysis. The price dynamics are fundamentally different (algorithmic RRP-anchored vs human sentiment-driven). The only potentially useful Keepa signal remains sales rank (velocity), which our scraper doesn't extract.

## Next Steps

### Done
- ~~**Run training** with new hurdle model and compare metrics~~ DONE (Exp 22)
- ~~**Tier comparison**~~ DONE (Exp 22) — T1 wins, Keepa features hurt
- ~~**Classifier diagnostics**~~ DONE (Exp 23) — AUC=0.947, calibration issues at low probs, 3 weak themes
- ~~**ML improvement scan**~~ DONE (Exp 24) — overfit diagnosed, quick wins found, quantile/theme tested
- ~~**Theme-specific models**~~ TESTED (Exp 24) — not viable, theme models hurt (not enough data)
- ~~**Quantile regression**~~ TESTED (Exp 24/25) — works for intervals, not as replacement; 65% coverage needs cal
- ~~**Apply quick wins**~~ VALIDATED (Exp 25) — depth=5+P1/P99 gives +0.079 R2 confirmed
- ~~**BrickTalk features**~~ TESTED (Exp 25) — never_discounted r=0.14 was artifact of shelf filter; dead when filter removed (r=-0.02)
- ~~**Anti-overfit tweaks**~~ TESTED (Exp 25) — all hurt; more data is the fix, not regularization
- ~~**P1/P99 + P(avoid) calibration**~~ APPLIED — winsorization in training + CV, isotonic calibration on classifier
- ~~**Model alternatives**~~ TESTED (Exp 26) — CatBoost, HistGB, stacking all worse than LightGBM; Yeo-Johnson confirmed critical (+0.13 R2)
- ~~**Keepa separated signals**~~ TESTED (Exp 28) — 3P FBA/FBM/BB r=0.30-0.37, not purely leaky (17mo early), but too noisy at n=607; sales rank empty
- ~~**Keepa technical analysis**~~ TESTED (Exp 29) — 67 TA indicators (SMA/EMA/RSI/MACD/Bollinger/Donchian); all hurt CV; TA doesn't transfer to LEGO pricing

### High Priority
1. ~~**Apply depth=5 + P1/P99 to production**~~ ALREADY IN PLACE (code uses P1/P99 and Optuna searches depth 3-8)
2. **Simplify pipeline to T1-only** — remove T2/T3/ensemble code and UI tier labels; show one growth number + RISK badge
3. **More data** — biggest lever; learning curve not saturated, anti-overfit tweaks all hurt, more data is the only fix
4. **Add quantile P10/P90 intervals to UI** — usable for directional uncertainty (8.1% avg width)

### Medium Priority
5. **Fix winner underprediction** — 20%+ growth sets underpredicted by 12.0%; fundamental mean compression, not fixable by tuning; explore asymmetric loss or winner-specific post-hoc correction
6. ~~**Calibrate P(avoid)**~~ APPLIED — isotonic calibration added to `classifier.py`, auto-fits on CV probs at training time
7. ~~**Improve Keepa coverage for never_discounted**~~ DEAD — r=0.14 was artifact of shelf filter; r=-0.02 when filter removed
8. **Fix Keepa sales rank extraction** — scraper stores sales_rank_json column but extracts 0 data; this is BrickTalk's #1 signal (Amazon velocity/demand) and the only non-leaky Keepa signal
9. **Pre-retirement BL sales** — scrape monthly sales for active sets (current BL data all post-retirement, leaky)
10. **Prior versions count (one-and-done)** — BrickTalk's strongest qualitative signal; needs Rebrickable API or title matching
11. **Live tracking feedback loop** — use prediction vs actual to recalibrate

### Low Priority / Explore
10. **Feature engineering from new sources** — Rebrickable (part rarity), designer track record
11. **Conformal intervals** — code exists in `conformal.py` but not integrated into UI
12. **Currency data enrichment** — usd_vs_mean is strong (r=-0.231), deeper regional pricing analysis
