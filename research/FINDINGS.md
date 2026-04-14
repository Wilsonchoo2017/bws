# Research Findings: LEGO Set Investment Return Prediction

27+ experiments across EDA, feature engineering, model tuning, portfolio optimization, model architecture, and model alternatives.

## Current Model (Classifier-only, BL ground truth + GT + Exp 34-35 features)

**Classifier-only architecture** (LightGBM, Exp 32 + 33 + 34 + 35):
1. **P(avoid)**: BL annualized return < 8%, asymmetric weights, F2-optimized
2. **P(great_buy)**: BL annualized return >= 20%, Optuna-tuned
3. **No regressor** -- buy categories determined purely by classifier probabilities
4. **43 features**: 36 Keepa+metadata (Exp 31+33+34+35) + 7 Google Trends (Exp 32)

**Buy Categories** (from classifiers):
- **WORST**: P(avoid) >= auto-tuned threshold (~0.18)
- **GREAT**: P(great_buy) >= auto-tuned threshold (~0.21)
- **GOOD**: P(great_buy) >= 0.10 (below GREAT threshold)
- **SKIP**: everything else

**Performance** (production training, 2026-04-10):
- Avoid classifier: AUC=0.820, F1=0.783, **Recall=98.7%**, threshold=0.15
- Great-buy classifier: AUC=0.783, F1=0.384, Recall=66.9%, threshold=0.17
- Training: 1116 sets with BL ground truth (from 2470 total retired <= 2024)
- GT coverage: 24.8% (661/2662 sets)

**Google Trends features** (Exp 32, YouTube search property):
- gt_avg_value (ranked #9/39 in feature importance)
- gt_pre_retire_avg, gt_peak_value, gt_months_active, gt_decay_rate
- gt_lifetime_months, gt_peak_recency
- All cut at retired_date during training (no lookahead)
- Exp 32 diagnostic: P(avoid) AUC +0.017, P(great_buy) AUC +0.006

**Avoid Classifier** (Munger inversion, BL ground truth + asymmetric weights):
- **Ground truth: BrickLink annualized returns** (1323 retired sets, BE pricing excluded)
- Keepa 3P FBA as fallback for sets without BL price data
- **Asymmetric sample weights**: strong loser (< -15%) = 3x, loser (-15% to -5%) = 2x, stagnant = 1x
- **F2 Optuna objective** (recall-weighted, beta=2)
- **Auto-tuned decision threshold** (max-F2 with precision >= 40%)
- Isotonic calibration on OOF probabilities (fixes low-prob overconfidence)
- Shown as RISK/WARN badges on UI (confidence bands: high >= 0.50, moderate >= 0.20)
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
28. **Binary 3P floor above RRP is the first working Keepa feature** -- `kp_fba_floor_above_rrp` gives +0.017 R2 in CV; 135 sets with 3P floor >= RRP grow 11.4% vs 8.8% (+2.5% delta); binary framing avoids the overfitting that killed continuous Keepa features
29. **3P avg premium is the strongest single feature for BL price prediction** -- Spearman r=0.547 with bl_current_vs_rrp; 7 of top 10 features are 3P-related; OOS frequency itself is weak, but the *price response* to OOS matters
30. **Keepa+BL model ranks sets well (Spearman 0.618) even at R2=0.34** -- for buy/skip decisions ranking > point estimates; top quintile averages 1.52x RRP vs bottom quintile 0.94x (0.58 separation)
31. **3P premium signal is universal across all cohorts** -- Spearman 0.3-0.7 in every retirement year (2020-2025), every major theme (Star Wars, City, Technic, HP), every price tier (2-7); not a theme artifact
32. **BE annual_growth_pct is a different (softer) target than actual BL market price** -- T1 R2=0.75 on BE growth vs R2=0.34 on BL price; BE target may be easier to predict because BE pricing model is smoother/more formulaic than real market
33. **Amazon review count is a strong demand proxy** -- r=0.487 Spearman; #2 feature by model importance; not leaky (reviews accumulate during retail life)
34. **12mo and 36mo BL targets don't work** -- R2~0 at 12mo (too noisy/early), R2~0 at 36mo (small n + different era); 24mo is the sweet spot (R2=0.19, n=225)
35. **Keepa data starts post-retirement for early-retired sets** -- sets retired before ~2020 may have Keepa data starting after retirement, making pre-retirement features empty; a data coverage limitation, not a methodology flaw
36. **OOS frequency features are completely dead** -- MI < 0.01 for ALL: amz_oos_pct, amz_oos_event_count, amz_oos_in_last_6mo, oos_pct_last_6/12mo, plus all OOS interaction terms. OOS itself doesn't predict appreciation; only the *price response* (3P premium) does
37. **Theme-aware corrections work** -- `theme_false_pos` (Dots/DUPLO/Holiday/Classic) and `theme_strong` (Star Wars/HP/Technic/Icons) add +0.07 R2; `3p_prem_adj` (3P premium discounted 50% for false-pos themes) ranks #5 by importance
38. **Excluding 2025+ sets improves model** -- barely-retired sets have meaningless BL prices (still near RRP); removing them changes training pool from 1043 to 876 but R2 jumps from 0.354 to 0.387
39. **Quintile separation is clean after iteration** -- Bottom 20% actual=0.96x RRP, Top 20% actual=1.58x RRP; all 5 quintiles are monotonically ordered (pred aligns with actual)
40. **2025 holdout: Spearman=0.453, R2=-0.73** -- model ranks 2025 sets reasonably well (0.45 rank corr) but R2 is negative because barely-retired sets haven't appreciated yet; model correctly predicts *some* will appreciate but BL prices haven't caught up
41. **Head-to-head on BL ground truth: Exp31 beats Prod T1 on R2 and bias** -- Exp31 R2=0.361, Prod T1 R2=-0.03; Exp31 bias=-0.03 vs Prod bias=-0.14; Exp31 MAE=0.208 vs Prod MAE=0.261; on 872 common retired sets
42. **Prod T1 still ranks older cohorts better** -- Prod Spearman: 2020=0.82, 2021=0.70, 2022=0.77 vs Exp31: 0.66, 0.59, 0.60; Prod's BE-trained theme encoding captures long-term appreciation patterns better for established cohorts
43. **Exp31 wins 15 of 25 themes** -- biggest wins: Vidiyo (+0.84), Dots (+0.46), Disney (+0.39), BrickHeadz (+0.38); Prod wins: Classic (-0.37), Duplo (-0.16), Hidden Side (-0.10), Harry Potter (-0.10), Icons (-0.09)
44. **BE value_new/RRP has highest raw Spearman (0.74) but +0.17 positive bias** -- BE systematically overestimates value; if de-biased it would be a strong baseline; but it IS the look-ahead data we're trying to replace
45. **Exp31 is the only model with positive R2 against BL truth** -- Naive R2=-0.38, BE R2=-0.07, Prod T1 R2=-0.03, Exp31 R2=+0.36; all others have negative R2 because they're calibrated to a different scale
46. **If model predicts >=10% growth, 74% actually grow, 63% exceed 10%** -- at >=20% threshold: 81% grow, 72% exceed 10%; at >=30%: 88% grow, 80% exceed 10%; the model is well-calibrated for positive calls
47. **41.6% of retired sets are "avoid" (BL < RRP)** -- much higher than the 20% loser rate under BE growth definition; many sets never appreciate above retail on BrickLink secondary market
48. **New classifier (AUC=0.870) underperforms old on BL loser detection** -- OLD model's negated growth has AUC=0.746 for finding BL losers, NEW dedicated classifier only 0.661; the old BE-trained model's growth prediction is a BETTER loser detector than a binary classifier trained on BL data. This suggests keeping the old classifier or using regressor scores directly
49. **Classifier is underconfident at low P(avoid)** -- at P=0.2-0.4, actual avoid rate is 47% but model says 25-35%; at P>0.5 calibration improves; needs isotonic recalibration
50. **Buy signal (P(avoid)<0.5 & pred>=15%) delivers 78.7% hit rate, +44.3% avg return** -- the strongest actionable signal; 1,156 sets qualify out of 2,428
51. **Lower thresholds dominate** -- F2-optimal thresholds are 0.20 for both avoid and great_buy; default 0.50 too conservative; tuned: +2.8% avg return, +3.6pp precision(20%), +32.5pp WORST recall
52. **P(great_buy) is temporally stable (AUC 0.72-0.78)** -- no degradation across 2022-2024 walk-forward; P(avoid) more volatile (0.56-0.85); great_buy generalizes better
53. **2024 holdout validates the model** -- 89.5% hit rate, 66.7% precision(>=20%) on 402 unseen sets; WORST recall=96.4%
54. **Regressor has -9.6% bias in 10-20% bucket** -- predicts +15.2% when actual +24.8%; mean compression persists; classifiers bypass this
55. **P(good_buy) classifier doesn't help** -- with tuned low thresholds, GOOD captures only 22 sets at -9.9% return; regressor fallback adequate
56. **Asymmetric loss improves ranking but not decisions** -- alpha=2 Huber gives +0.033 Spearman but buy decisions unchanged (classifier-driven)
57. **P(great_buy) alone ranks better than regressor** -- Spearman 0.547 vs 0.533; classifier probability is a better ranking signal
58. **Best ensemble is marginal** -- blended signals add +0.022 Spearman max; not worth complexity
59. **NEW system dominates on BL ground truth** -- +4.1% higher avg return (20.6% vs 16.6%), +11.4pp precision(>=20%), 98.1% WORST recall; buys 192 sets vs 429 but each buy is higher quality
60. **BL-trained inversion is strictly better than BE-trained** -- AUC +0.005, recall +7.3pp, FN -58 on BL truth; compounds with P(great_buy) into +4.1% portfolio gain
61. **Only 6 losers slip through the new system** -- vs 33 old; BL+weights avoid + P(great_buy) forms extremely tight filter
62. **GREAT category delivers +21.6% annualized on BL** -- 150 sets, 97.3% positive rate, median +17.7%
63. **258 borderline sets correctly skipped** -- OLD system buys at +13.5% avg but includes 29 losers; NEW trades quantity for certainty
59. **BL ground truth + asymmetric weights cut classifier FN by 44%** -- switching target from BE annual_growth_pct to BL annualized returns (1319 retired sets) and weighting severe losers 3x: FN 133->75, recall 83.2%->90.5%; strong losers now 1% miss rate (was 5%); AUC 0.808->0.813
60. **F2 Optuna objective + lowered threshold boost recall** -- F2 (recall 4x precision) replaces AUC as Optuna objective; auto-tuned threshold ~0.30 (vs default 0.50); on BE target alone: FN 139->59 (-57%), recall 84.7%->93.5%, precision 80.4%->77.1%
61. **Asymmetric weights specifically fix severe losers** -- strong losers (<-15%) down to 1% miss (1/79), losers (-15% to -5%) down to 4% miss (6/157), stagnant 9% miss (37/416); weighting concentrates model attention on costly mistakes
62. **scale_pos_weight is more effective than is_unbalance** -- Optuna consistently selects SPW ~4.5; SPW=3.0 gives best F2 in ablation; explicit class weight outperforms LightGBM's automatic balancing
63. **Minecraft FN fixed by F2 tuning** -- miss rate dropped from 93% (baseline) to 7% (F2-tuned) on BE target; from 50% to 19% on BL ground truth; the F2 objective alone resolved the worst blind spot

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
| 30 | 3P spread (BrickTalk exact) | 642 | fba_floor +0.017 | Binary "3P floor above RRP" = first Keepa feature to improve CV; 135 sets, +2.5% avg growth delta; added to pipeline |
| 31 | Keepa+BL pure signal | 1043 | Spearman 0.618 | BE pricing/growth EXCLUDED; Keepa+BL only; 3P premium is #1 feature (r=0.547); model ranks sets well (Spearman 0.618) despite R2=0.34 on BL current price target; features stable across all cohorts |
| 31b | Feature selection + failure | 1043 | 20 features, Sp=0.624 | MI+redundancy+LOFO: 56->20 features; OOS frequency features all dead (MI<0.01); winners underpredicted -0.42 bias; Dots/DUPLO/Holiday false positives; 56 false negatives from missing Keepa |
| 31c | Iterated model | 876 | R2=0.387, Sp=0.646 | Excluded 2025+; theme penalty+strong features; missing Keepa proxy; Optuna tuned; +0.032 R2, +0.022 Spearman; quintile separation clean (0.96->1.58); 2025 holdout Spearman=0.453 |
| 31d | Model comparison | 872 | Exp31 wins 15/25 themes | Head-to-head vs Prod T1 on BL ground truth: Exp31 R2=0.361 vs Prod R2=-0.03; Exp31 Spearman=0.644 vs Prod=0.574; BUT Prod ranks better for 2020-2022 cohorts; BE value_new has best Spearman (0.74) but +0.17 bias |
| 31e | Production deploy + calibration | 2428 | CV R2=0.261, AUC=0.870 | Model trained and saved; pred>=10% hit rate 74% (>0%), 63% (>10%); pred>=20% hit rate 81%; classifier AUC=0.870; OLD classifier AUC=0.746 on BL losers -- old model still detects losers better via negated growth |
| 31f | P(great_buy) classifier | 876 | AUC=0.786 | Dedicated binary classifier for P(growth>=20%); 4-tier buy categories (GREAT/GOOD/SKIP/WORST); reframes buying decision from regression to classification |
| 31g | Improvement evaluation | 2448 | Threshold tuning wins | Tuned thresholds: +2.8% avg return, +3.6pp precision(20%), +32.5pp WORST recall; P(good_buy) classifier, asymmetric loss, ensembles all neutral/negative; P(great_buy) temporally stable (AUC 0.72-0.78 across years) |
| 31h | Combined system eval | 1291 | +4.1% return, 98.1% recall | BL+weights inversion + P(great_buy) evaluated on 1291 BL ground truth sets; NEW system: 192 buys at +20.6% avg return (vs OLD 429 buys at +16.6%); only 6 losers bought (vs 33); WORST recall 98.1% (vs 79.9%); portfolio +14.7% over buying all sets |
| 23b | FN minimization | 2631 | FN 139->59 (-57%) | F2 Optuna objective + auto-tuned threshold=0.30 + scale_pos_weight; Minecraft miss 93%->7%; recall 84.7%->93.5%; AUC 0.940->0.967; precision 80.4%->77.1% (acceptable tradeoff) |
| 23c | BL ground truth + asymmetric loss | 1294 | FN 133->75 (-44%) | BL annualized returns replace BE annual_growth_pct; asymmetric weights (3x strong loser, 2x loser); strong losers 1% miss rate; recall 83.2%->90.5%; AUC 0.808->0.813 on BL labels |

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

## Experiment 23b: FN Minimization (2026-04-10)

Three-pronged approach to aggressively minimize classifier false negatives (missed losers).

### Approach
1. **F2 Optuna objective**: Replaced AUC with F-beta (beta=2, recall weighted 4x over precision)
2. **Auto-tuned threshold**: Sweeps 0.15-0.55, picks threshold maximizing F2 with precision >= 40%
3. **scale_pos_weight**: Added to Optuna search space [1.5, 5.0], replaces is_unbalance

### Results (2631 sets, BE target, threshold=0.30)
- **FN: 139 -> 59 (-57%)**, recall 84.7% -> 93.5%, AUC 0.940 -> 0.967
- Precision 80.4% -> 77.1% (acceptable tradeoff)
- **Minecraft miss rate: 93% -> 7%** (the single biggest blind spot fixed)
- Dots: 9% -> 9% (stable), Harry Potter: 58% -> 58% (needs red flags)
- scale_pos_weight: Optuna consistently picks ~4.5; SPW=3.0 best in ablation
- F2-tuned model at threshold=0.30: F2=0.897

### Code Changes
- `classifier.py`: `_find_recall_threshold` (max-F2 sweep), F2 Optuna objective, scale_pos_weight in search space, decision_threshold field on TrainedClassifier, sample_weight threading
- `inversion_model.py`: confidence bands shifted (high >= 0.50, moderate >= 0.20)

## Experiment 23c: BL Ground Truth + Asymmetric Loss (2026-04-10)

Switched classifier training target from BE annual_growth_pct to BrickLink actual market prices.

### Ground Truth Construction
- **Primary**: BL current_new price (MYR / 4.4 for USD) vs RRP, annualized by years since retirement
- **Fallback**: Keepa 3P FBA latest price vs RRP (for sets without BL data)
- **Excluded**: Sets without retired_date (can't annualize)
- **Result**: 1319 sets with BL annualized returns (down from 2700 BE sets)

### BL vs BE Target Comparison
- BL avoid rate: 61% (at 8% threshold) vs BE avoid rate: 55% -- BL is stricter
- BL tiers: 79 strong losers, 157 losers, 418 stagnant, 474 neutral, 168 performers
- Correlation between BL and BE returns: r=0.345 (substantially different targets)

### Asymmetric Sample Weights
- Strong loser (< -15%): weight 3.0
- Loser (-15% to -5%): weight 2.0
- Stagnant (-5% to 5%) and keepers: weight 1.0
- Implemented via `compute_avoid_sample_weights()`, threaded through all clf training functions

### Results (1294 sets, evaluated against BL labels, threshold=0.30)

| Model | AUC | Recall | FN | Strong Loser Miss |
|-------|-----|--------|----|--------------------|
| BE target (baseline) | 0.808 | 83.2% | 133 | 5% |
| BL target | 0.814 | 88.6% | 90 | 4% |
| BL + weights | 0.813 | 90.5% | 75 | **1%** |

### Per-Theme (BL + weights)
- Friends: 0% miss, City: 0% miss, Monkie Kid: 0% miss
- Minecraft: 19% miss (down from 50% on BE), Harry Potter: 18%, Star Wars: 19%
- Weak: Creator 38% miss, BrickHeadz 40%, Icons 38%

### Code Changes
- `pg_queries.py`: `load_bl_ground_truth()` -- BL annualized returns + Keepa fallback
- `classifier.py`: `compute_avoid_sample_weights()` + sample_weight parameter threading
- `training.py`: classifier now loads BL ground truth at training time

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

### Discount-during-retail RE-TEST (Exp 36)
The "signal is dead" verdict above came from a binary `never_discounted` cutoff. Re-tested with continuous, depth-weighted, in-stock-aware variants on the 43-feature classifier baseline (Avoid AUC 0.8001, Great-Buy AUC 0.7293):

| Feature | ΔAvoid | ΔGB | LOFO | Corr w/ existing |
|---|---|---|---|---|
| `amz_discount_depth_x_freq` | **+0.0071** | +0.0028 | HELPS | 0.67 vs max_discount |
| `amz_discount_episodes` | **+0.0064** | -0.0019 | HELPS | 0.04 (uncorrelated) |
| `amz_discount_pct_last_12mo` | **+0.0057** | +0.0009 | HELPS | 0.77 |
| `amz_discount_pct_last_6mo` | +0.0008 | **+0.0068** | HELPS | 0.76 |
| `amz_avg_discount_when_discounted` | +0.0050 | +0.0024 | NEUTRAL | 0.91 redundant |

- All 5 use `_cut(retired_date)` Amazon 1P + `rrp_usd_cents` from BrickEconomy, in-stock-only denominators.
- Cumulative GROUP_A (all 5): +0.0075 Avoid, +0.0070 GB.
- **Productionized**: only `amz_discount_depth_x_freq` (= `avg_discount_pct × pct_below_95rrp`). Cleanest signal, lowest collinearity. Added to `KEEPA_BL_FEATURES` (now 37).
- **OOS-timing features (Exp 31:280-327) prototyped + tested**: `amz_first_oos_months_before_retire`, `amz_final_oos_to_retire_days`, `amz_restocked_after_final_oos`. All weak vs the 43-feature baseline (best ΔAUC +0.0020, group cumulative -0.0036 on Great-Buy). **Not productionized.**
- **Corrected verdict**: discount history IS predictive when formulated as a continuous depth × frequency composite. The original "dead" finding was a thresholding artifact, not a data limitation. The binary `never_discounted` erased the magnitude signal.
- See `research/growth/36_retail_demand_signals.py`.

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

## Experiment 30: 3P Spread Analysis — BrickTalk's Exact Signal (2026-04-07)

Tested BrickTalk's specific framing: "has the 3P FBA minimum price stayed above retail?" as a binary demand signal.

### BrickTalk Signal Validation

| Group | n | Avg Growth | Median |
|-------|---|-----------|--------|
| 3P floor ABOVE RRP | 135 | **11.4%** | **9.7%** |
| 3P floor below RRP | 507 | 8.8% | 6.6% |
| **Delta** | | **+2.5%** | **+3.2%** |

Amazon-discounting-while-3P-holds divergence:
- Q1 (both discounting): 7.4% growth
- Q4 (Amazon cheap, 3P premium): 10.3% growth
- Clean monotonic gradient across quartiles

### CV Results (features with positive delta)

| Feature | R2 | Delta |
|---------|-----|-------|
| T1 only (642 sets) | 0.278 | baseline |
| + **kp_fba_floor_above_rrp** (binary) | **0.295** | **+0.017** |
| + spread_bb_last_vs_rrp | 0.287 | +0.008 |
| + spread_fbm_mean_vs_rrp | 0.286 | +0.008 |
| + spread_fba_never_below_rrp | 0.282 | +0.004 |
| + spread_fba_floor_vs_rrp (continuous) | 0.280 | +0.002 |
| + top 3 combined | 0.222 | -0.056 |

### Why Binary Works Where Continuous Failed

`kp_fba_floor_above_rrp` is the **first Keepa feature to improve CV**. The binary framing succeeds because:
1. It captures a categorical distinction (demand > supply sets) without overfitting to price magnitude
2. It's robust to price noise -- a set either maintained 3P above retail or it didn't
3. Combining multiple continuous spread features causes collinearity and overfitting

### Added to Pipeline

Added to `TIER2_FEATURES` and `engineer_keepa_features()`:
- `kp_fba_floor_above_rrp` -- binary: min 3P FBA price >= 98% RRP
- `kp_fba_floor_vs_rrp` -- continuous: min 3P FBA vs RRP %
- `kp_fbm_mean_vs_rrp` -- continuous: mean 3P FBM vs RRP %
- `kp_fba_never_below_rrp` -- binary: all 3P FBA prices >= 95% RRP

Feature selection (MI + LOFO) will prune any that don't survive in production training.

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
5. ~~**Fix winner underprediction**~~ REFRAMED (Exp 31f) — instead of fixing regression bias (-12.8%), added P(great_buy) classifier that directly predicts P(growth>=20%); classification bypasses mean compression entirely; 4-tier buy categories (GREAT/GOOD/SKIP/WORST) replace old BUY/HOLD/AVOID
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

## Experiment 31: Keepa + BrickLink Pure Signal (2026-04-09)

Stripped all BE pricing/growth data. Used only Keepa + BrickLink market signals + BE factual metadata (theme, pieces, minifigs, RRP, etc). Target: BrickLink current new price / RRP (real secondary market price).

### Design
- **BE forbidden**: annual_growth_pct, value_new_cents, future_estimate, rolling_growth, subtheme_avg_growth, theme_rank, distribution_mean/stddev
- **BE allowed**: theme, subtheme, pieces, minifigs, RRP, rating, reviews, designer, exclusive_minifigs, retired_date, release_date
- **Features**: 67 total across 11 categories — Amazon OOS patterns (9), restock behavior (5), 3P price response to OOS (7), 3P price trend (14), Amazon 1P dynamics (7), demand proxy (3), metadata (12), data quality (3), metadata x market interactions (8)
- **All Keepa features cut at retired_date** to prevent lookahead bias
- **BL monthly sales used only as targets** (post-retirement data)

### Dataset
- 1,043 sets with `bl_current_vs_rrp` target (99.5% coverage)
- 881 sets with Keepa + retired_date overlap
- `sales_rank_json` confirmed empty (0 data points) — demand proxy features dropped

### Top Features (Spearman with bl_current_vs_rrp)

| Rank | Feature | Spearman | Category |
|------|---------|----------|----------|
| 1 | `3p_avg_premium_vs_rrp_pct` | +0.547 | 3P Trend |
| 2 | `3p_above_rrp_pct` | +0.521 | 3P Trend |
| 3 | `3p_fba_vs_amz_avg_spread` | +0.495 | 3P Trend |
| 4 | `3p_price_during_oos_vs_rrp` | +0.494 | OOS Response |
| 5 | `amz_review_count` | +0.487 | Demand |
| 6 | `bb_premium_during_oos_pct` | +0.474 | OOS Response |
| 7 | `3p_max_premium_vs_rrp_pct` | +0.473 | 3P Trend |
| 8 | `3p_price_at_retire_vs_rrp` | +0.472 | 3P Trend |
| 9 | `3p_above_rrp_last_6mo_pct` | +0.466 | 3P Trend |
| 10 | `3p_premium_x_price_tier` | +0.453 | Interaction |

### LightGBM Results (5-fold GroupKFold by retirement year)

**bl_current_vs_rrp target:**
- OOF R2 = 0.344, Mean fold R2 = 0.227 +/- 0.057
- **OOF Spearman rank correlation = 0.618** (strong ranking ability)
- Top quintile: 1.52x RRP, Bottom quintile: 0.94x RRP, Separation: 0.58
- Top importance: `3p_avg_premium_vs_rrp_pct` (gain=818), `amz_review_count` (559), `minifig_value_ratio` (458)

**annualized_return target:**
- OOF R2 = 0.214, Spearman = 0.498
- Weaker; 2019+2025 fold is the hardest (R2=0.02)

**Multi-horizon:**
- 12mo: R2 ~ 0 (too noisy at short horizon, n=265)
- 24mo: R2 = 0.19 (sweet spot, n=225)
- 36mo: R2 ~ 0 (small n + different era, n=220)

### Cohort Stability
- `3p_avg_premium_vs_rrp_pct` Spearman by retirement year: 2020=0.52, 2021=0.29, 2022=0.50, 2023=0.49, 2024=0.49, 2025=0.32 — **consistent across all years**
- Works within themes: Star Wars 0.65, Technic 0.67, City 0.67, Disney 0.64, Town 0.68, HP 0.44
- Works across price tiers: Tier 2=0.57, Tier 3=0.57, Tier 4=0.55, Tier 5=0.47, Tier 6=0.57 (Tier 1 weaker at 0.29)

### Validation: 76173 (Spider-Man vs Carnage, 19.9% annual growth)
- 4 OOS episodes, 6% OOS, 3P above RRP 73%, 3P premium 28%, 3P at retirement 1.61x RRP
- Buy box premium during OOS: 66% — all strong signals confirmed

### Key Insight
The R2=0.34 vs T1 R2=0.75 gap is partly because the targets differ. T1 predicts BE's `annual_growth_pct` (BE's own pricing model output, smoother). Exp 31 predicts actual BrickLink market prices (noisier but ground truth). The Spearman=0.618 ranking power is the more relevant metric for investment decisions.

## Experiment 31f: P(great_buy) Classifier (2026-04-10)

Reframed the buying decision from regression (predict exact growth %) to classification (predict "is this a Great Buy?"). The regressor suffers from -12.8% mean compression on winners, but the model already ranks well (Spearman=0.618). Classification bypasses mean compression entirely.

### Motivation
- Regressor compresses toward mean: 20%+ growth sets underpredicted by -12.8%
- 2025/2026 sets cluster just below 20% — model lacks confidence to push higher
- User's actual decision is binary: **buy or not buy**, not "predict exact growth"
- Finding 46: model already well-calibrated for positive calls (81% accuracy at 20% threshold)

### Architecture Change

**Old decision logic** (regression-driven):
```
IF P(avoid) >= 0.5  -> AVOID
ELIF growth >= 8%   -> BUY
ELSE                -> HOLD
```

**New decision logic** (classifier-driven):
```
IF P(avoid) >= 0.5          -> WORST   (never buy)
ELIF P(great_buy) >= 0.6    -> GREAT   (buy)
ELIF regressor >= 10%       -> GOOD    (buy if conditions right)
ELSE                        -> SKIP    (don't buy)
```

### Implementation
- P(great_buy) classifier: LightGBM binary, same 26 Keepa+metadata features
- Trained with `invert=True` (positive class = growth >= 20%, not growth < threshold)
- Reuses same infrastructure: Optuna tuning, isotonic calibration, OOF threshold tuning
- Regressor stays for ranking within categories (which "GREAT" sets are best?)
- P(avoid) stays for bottom-end detection (AUC=0.961)

### Expected Performance
- ~17% positive class rate (149/876 sets grow 20%+)
- Expected AUC 0.80-0.90 based on existing ranking quality
- Class imbalance handled via `is_unbalance=True` + `scale_pos_weight` (Optuna-tuned)

### Key Findings
47. **Classification > regression for buying decisions** — the user doesn't need exact growth %, they need P(growth>=20%). The regressor's Spearman=0.618 ranking ability directly translates to classification AUC
48. **Mean compression is irrelevant for classifiers** — binary P(great_buy) doesn't suffer from the -12.8% bias that cripples regression predictions for winners
49. **4-tier categories are more actionable** — GREAT/GOOD/SKIP/WORST maps directly to portfolio actions vs ambiguous growth percentages

### Roadmap: Further Improvements (updated after Exp 31g)

**High Priority — DONE (Exp 31g):**
1. ~~Tune GREAT_BUY_THRESHOLD~~ — **DONE**: optimal=0.20; +2.8% avg return, +32.5pp WORST recall
2. ~~Walk-forward validation~~ — **DONE**: P(great_buy) AUC stable 0.72-0.78 across years
3. ~~Calibrate for 2024 sets~~ — **DONE**: 89.5% hit rate, 66.7% precision(>=20%), WORST recall=96.4%

**Medium Priority — EVALUATED, SKIP:**
4. ~~P(good_buy) classifier~~ — **SKIP**: -0.7pp precision; GOOD category too small with tuned thresholds
5. ~~Asymmetric loss~~ — **SKIP**: +0.033 Spearman but no decision impact (classifier-driven)
6. ~~Ensemble signals~~ — **SKIP**: +0.022 Spearman max; marginal

**Low Priority / Explore:**
7. **Multi-class ordinal classifier** — directly predict 4 categories instead of combining two binary classifiers + regressor
8. **Dynamic thresholds** — adjust GREAT_BUY_THRESHOLD based on market conditions (more conservative in uncertain markets)

## Experiment 31g: Priority Improvements Evaluation (2026-04-10)

Systematic evaluation of 6 improvements on 2448 training sets (retired <= 2024), using GroupKFold OOF predictions. Each improvement measured in isolation and combined.

### Baseline (Exp 31f architecture)

| Metric | Value |
|--------|-------|
| Regressor OOF R2 | 0.263 |
| Regressor Spearman | 0.533 |
| P(avoid) AUC | 0.687 |
| P(great_buy) AUC | 0.786 |
| Great-buy positive rate | 37.2% (910/2448) |
| Avoid rate | 41.3% (1011/2448) |

Baseline buy decision (avoid=0.5, great=0.5, good=regressor>=10%):
- BUY: n=1369, avg_return=+39.0%, hit_rate=74.3%, precision(>=20%)=53.4%
- WORST recall: 45.7%

### Improvement 1: Threshold Tuning -- THE WINNER

Swept avoid and great_buy thresholds from 0.20-0.75, optimizing F2 (recall-weighted).

**Best thresholds**: avoid=0.20, great_buy=0.20

| Config | Buy n | Avg Return | Hit(>0%) | Prec(20%) | WORST Recall |
|--------|-------|------------|----------|-----------|--------------|
| Baseline (0.5/0.5) | 1369 | +39.0% | 74.3% | 53.4% | 45.7% |
| **Tuned (0.20/0.20)** | **867** | **+41.8%** | **76.8%** | **57.0%** | **78.2%** |
| Delta | -502 | **+2.8%** | **+2.5pp** | **+3.6pp** | **+32.5pp** |

The tuned model is more selective (867 vs 1369 buys) but significantly better:
- **Higher quality buys**: +2.8% average return, +3.6pp precision for 20%+ growth
- **Much better loser detection**: WORST recall 45.7% -> 78.2% (catches 78% of all losers)
- Trade-off: more sets classified as WORST (787 -> 1560), some good sets may be missed

50. **Lower thresholds dominate** -- F2-optimal thresholds are 0.20 for both avoid and great_buy; the default 0.50 is far too conservative; auto-tuned `_find_recall_threshold()` in production should converge near this

### Improvement 2: Walk-Forward P(great_buy) Stability

Temporal walk-forward: train on years < test_year, evaluate on test_year.

| Test Year | n | n_great | AUC(great) | AUC(avoid) | Regressor R2 | Spearman |
|-----------|---|---------|------------|------------|--------------|----------|
| 2022 | 226 | 134 | **0.783** | **0.850** | 0.265 | 0.573 |
| 2023 | 1580 | 518 | 0.719 | 0.556 | 0.163 | 0.478 |
| 2024 | 402 | 107 | 0.732 | 0.719 | 0.185 | 0.520 |

51. **P(great_buy) is temporally stable (AUC 0.72-0.78)** -- no degradation trend; P(avoid) is more volatile (0.56-0.85); the great_buy classifier generalizes better than the avoid classifier across unseen years
52. **2023 is the hard year** -- P(avoid) AUC drops to 0.556, regressor R2=0.163; likely a large cohort with mixed outcomes; P(great_buy) holds up (0.719)

### Improvement 3: 2024 Holdout (Newly-Retiring Calibration)

Train on <= 2023, test on 2024 (402 sets).

**Regressor**: R2=0.185, Spearman=0.520, Bias=-4.1%

| Pred Bucket | n | Avg Actual | Avg Pred | Bias | Hit(>0%) |
|-------------|---|-----------|----------|------|----------|
| <0% | 160 | -0.8% | -8.4% | -7.6% | 39.4% |
| 0-10% | 96 | +6.2% | +4.5% | -1.6% | 60.4% |
| 10-20% | 74 | +24.8% | +15.2% | -9.6% | 79.7% |
| 20-50% | 67 | +25.7% | +31.1% | +5.3% | 76.1% |

**Classifiers on 2024**: P(great_buy) AUC=0.732, P(avoid) AUC=0.719

**Buy decision on 2024 holdout (tuned thresholds)**:
- BUY: n=57, avg_return=**+35.4%**, hit_rate=**89.5%**, precision(>=20%)=**66.7%**
- WORST recall=**96.4%** (catches nearly all losers)

53. **2024 holdout validates the model** -- 89.5% hit rate and 66.7% precision for 20%+ growth on unseen 2024 sets; WORST recall=96.4% means only 3.6% of actual losers slip through
54. **Regressor has -9.6% bias in the 10-20% growth bucket** -- predicts +15.2% when actual is +24.8%; mean compression persists for moderate winners; classifiers bypass this

### Improvement 4: P(good_buy) Classifier -- NEGATIVE

P(good_buy) AUC=0.737 (growth >= 10% positive class: 46.8%).

| Config | Buy n | Avg Return | Prec(20%) | Delta |
|--------|-------|------------|-----------|-------|
| Tuned baseline | 867 | +41.8% | 57.0% | - |
| With P(good_buy) | 878 | +41.2% | 56.3% | **-0.7pp** |

55. **P(good_buy) classifier doesn't help** -- with tuned low thresholds (0.20), nearly all sets are classified as GREAT or WORST; GOOD category captures only 22 sets with -9.9% avg return; the regressor fallback was already adequate for the few middle-ground sets

### Improvement 5: Asymmetric Loss -- NEGATIVE for decisions

| Alpha | OOF R2 | Spearman | Bias(20%+) | MAE(20%+) |
|-------|--------|----------|-----------|-----------|
| 1.0 (baseline) | 0.115 | 0.515 | -48.0% | 50.3% |
| 1.5 | 0.167 | **0.541** | -46.5% | 48.6% |
| **2.0** | 0.043 | **0.548** | **-43.1%** | **47.6%** |
| 3.0 | 0.149 | 0.498 | -47.0% | 48.6% |
| 5.0 | 0.111 | 0.509 | -48.9% | 50.1% |

Alpha=2.0 gives best Spearman (+0.033) and reduces winner bias by 5pp, but R2 collapses and buy decisions are unchanged.

56. **Asymmetric loss improves ranking but not decisions** -- alpha=2.0 Huber improves Spearman from 0.515 to 0.548 and reduces winner bias from -48% to -43%; but buy decisions are classifier-driven so the regressor improvement doesn't propagate; not worth the R2 trade-off

### Improvement 6: Ensemble Strategies -- MARGINAL

| Strategy | Spearman | Top20% Avg | Top20% Hit(>=20%) |
|----------|----------|-----------|-------------------|
| Regressor only | 0.533 | +64.6% | 73.6% |
| P(great_buy) only | 0.547 | +64.0% | 75.3% |
| **0.5*Reg + 0.5*P(great)*50** | **0.555** | +64.6% | 74.6% |
| P(great)*(1-P(avoid))*Reg | 0.529 | **+64.8%** | **76.5%** |

57. **P(great_buy) alone ranks better than the regressor** -- Spearman 0.547 vs 0.533; the classifier's probability is a better ranking signal than predicted growth %; confirms classification > regression for this problem
58. **Best ensemble is marginal** -- blended `0.5*Reg + 0.5*P(great)*50` gives Spearman=0.555 (+0.022 over regressor, +0.008 over classifier alone); not enough improvement to justify complexity; `P(great)*(1-P(avoid))*Reg` has best top-20% hit rate (76.5%) but worse overall ranking

### Summary Table

| Improvement | Impact | Verdict |
|-------------|--------|---------|
| 1. Threshold tuning | +2.8% return, +32.5pp WORST recall | **IMPLEMENT** |
| 2. Walk-forward stability | AUC 0.72-0.78 across years | **VALIDATED** |
| 3. 2024 holdout | 89.5% hit rate, 96.4% WORST recall | **VALIDATED** |
| 4. P(good_buy) classifier | -0.7pp precision | **SKIP** |
| 5. Asymmetric loss | +0.033 Spearman, no decision impact | **SKIP** |
| 6. Ensemble strategies | +0.022 Spearman max | **SKIP** |

### Action Items

1. **Verify production auto-tuned thresholds align with 0.20** -- the `_find_recall_threshold()` function in `classifier.py` should converge near 0.20; if not, hardcode override
2. **Monitor P(great_buy) AUC on 2025 cohort** -- walk-forward shows stability but 2025 data is scarce; track as more sets retire and BL prices stabilize
3. **Consider dropping GOOD category** -- with tuned thresholds, GOOD captures <2% of sets; simplify to GREAT/WORST/SKIP (3-tier)

### Remaining Alpha Opportunities

- **More training data** -- n=2448 is 2.5x the original 876 from Exp 31c; learning curve still climbing
- **Sales rank features** -- still empty in DB; this is the #1 potential new signal (Amazon velocity)
- **Prior versions count** -- "one-and-done" sets (no prior version) have higher growth; needs Rebrickable data

## Experiment 31h: Combined System Evaluation (2026-04-10)

Full pipeline evaluation on 1291 sets with BrickLink ground truth (annualized returns). Tests how the improved BL-trained inversion classifier works together with the growth prediction model (regressor + P(great_buy)).

### Setup

Two separate model pipelines evaluated on the **same 1291 BL ground truth sets**:
1. **Inversion classifier** (avoid gate): 3 variants -- BE-trained (old), BL-trained, BL+asymmetric weights (new)
2. **Growth model**: Keepa+BL regressor (R2=0.333, Sp=0.538) + P(great_buy) classifier (AUC=0.707)

### Phase 1: Inversion Classifier on BL Ground Truth

| Variant | AUC | Recall | Precision | F2 | FN |
|---------|-----|--------|-----------|----|----|
| BE target (old) | 0.808 | 83.2% | 75.8% | 0.816 | 133 |
| BL target | 0.814 | 88.6% | 73.5% | 0.851 | 90 |
| **BL + weights** | **0.813** | **90.5%** | **73.0%** | **0.864** | **75** |

BL+weights reduces false negatives by 44% (133 -> 75), especially for severe losers (5% -> 1% miss rate for <-15% sets).

### Phase 2: Head-to-Head -- OLD vs NEW System

| Metric | OLD | NEW | Delta |
|--------|-----|-----|-------|
| Buy signals | 429 | 192 | -237 |
| Buy avg BL return | +16.6% | **+20.6%** | **+4.1%** |
| Buy hit rate (>0%) | 92.3% | **96.9%** | **+4.6pp** |
| Buy precision (>=20%) | 26.6% | **38.0%** | **+11.4pp** |
| WORST signals | 704 | 1089 | +385 |
| WORST recall | 79.9% | **98.1%** | **+18.2pp** |
| Losers bought | 33 | **6** | **-27** |

OLD system: BE avoid (>=0.50) + regressor (>=8%) buy signal.
NEW system: BL+weights avoid (>=0.20) + P(great_buy)(>=0.20) + regressor (>=10%).

### Phase 3: Category Breakdown (BL Ground Truth)

| Category | n | Avg BL Return | Hit >0% | Hit >=20% | Median |
|----------|---|---------------|---------|-----------|--------|
| **GREAT** | **150** | **+21.6%** | **97.3%** | **40.7%** | **+17.7%** |
| GOOD | 42 | +17.3% | 95.2% | 28.6% | +14.6% |
| SKIP | 10 | +9.1% | 80.0% | 30.0% | +5.4% |
| WORST | 1089 | +3.4% | 62.8% | 8.3% | +3.0% |

GREAT sets average +21.6% annualized BL return with 97.3% positive rate. WORST sets average only +3.4% with 37.2% losing money. Clean separation.

### Phase 4: Portfolio Impact

| Strategy | n | Portfolio Return | vs Buy All |
|----------|---|-----------------|-----------|
| Buy ALL sets | 1291 | +6.0% | -- |
| OLD system | 429 | +16.6% | +10.6% |
| **NEW system** | **192** | **+20.6%** | **+14.7%** |

The new system generates **+14.7% excess return over buying all sets**, vs +10.6% for the old system. More selective (192 vs 429 buys) but higher quality.

### Phase 5: System Disagreement

| Agreement | n | Avg BL Return | Hit >0% |
|-----------|---|---------------|---------|
| Both buy | 171 | +21.2% | 97.7% |
| Both skip | 841 | +0.3% | 55.1% |
| OLD buys, NEW skips | 258 | +13.5% | 88.8% |
| NEW buys, OLD skips | 21 | +16.4% | 90.5% |

258 sets the OLD system would buy but NEW skips: avg return +13.5%, only 11% are actual losers. These are **borderline sets** -- profitable on average but below the NEW system's quality bar. The NEW system correctly trades quantity for quality.

### Key Findings

59. **NEW system dominates on BL ground truth** -- +4.1% higher avg return, +11.4pp better precision for 20%+ growth, catches 98.1% of losers (vs 79.9%); buys fewer sets (192 vs 429) but each buy is much higher quality
60. **BL-trained inversion classifier is strictly better than BE-trained** -- on BL ground truth, AUC +0.005, recall +7.3pp, FN -58; the improvement compounds with P(great_buy) into a +4.1% portfolio return gain
61. **Only 6 losers slip through the new system** -- vs 33 in the old system; combined BL+weights avoid (thresh=0.20) + P(great_buy) forms an extremely tight filter; 98.1% of all BL losers are caught
62. **GREAT category delivers +21.6% annualized on BL** -- 150 sets, 97.3% positive rate, median +17.7%; this is the core actionable signal for portfolio construction
63. **258 borderline sets correctly skipped** -- OLD system would buy these (avg +13.5%), but they include 29 actual losers; NEW system trades this quantity for higher certainty on the 192 it does buy

## Experiment 32: Google Trends Re-test + Classifier-only Architecture (2026-04-10)

Re-tested Google Trends (GT) with the current production pipeline (2459 sets, BL ground truth). Previous tests (Exp 16, 19b) at n=78-346 found GT dead. With 2400+ sets and BL ground truth, GT shows positive signal for classifiers.

### Phase 1: Quick Diagnostic

7 GT features engineered (all pre-retirement, no lookahead): gt_peak_value, gt_avg_value, gt_months_active, gt_decay_rate, gt_pre_retire_avg, gt_lifetime_months, gt_peak_recency.

| Metric | Baseline | +GT | Delta |
|--------|----------|-----|-------|
| P(great_buy) AUC | 0.7855 | 0.7917 | **+0.006** |
| P(avoid) AUC | 0.6874 | 0.7042 | **+0.017** |
| Regressor R2 | 0.2687 | 0.2549 | -0.014 |

Correlations (GT subset, n=658): gt_pre_retire_avg Sp=+0.398, gt_avg_value Sp=+0.358. gt_avg_value ranked #9/33 in feature importance. GT coverage: 24.9% (659/2650 sets).

### Phase 2: Production Integration

GT features added to classifiers only (not regressor). CLASSIFIER_FEATURES = 26 Keepa+metadata + 7 GT = 33 total. Regressor removed entirely -- classifier-only architecture.

Production training (2026-04-10):
- P(avoid): AUC=0.779, Recall=97.8%, threshold=0.15 (33 features)
- P(great_buy): AUC=0.725, Recall=64.3%, threshold=0.25 (33 features)
- Training: 5.0 minutes (was 5.8 with regressor)
- Inference: 2740 sets scored (106 GREAT, 168 GOOD, 72 SKIP, 2394 WORST)

### Key Findings

64. **GT helps classifiers, not regressor** -- P(avoid) +0.017 AUC, P(great_buy) +0.006 AUC, but regressor R2 drops -0.014; GT captures "collector awareness" that classifies well but doesn't predict exact growth
65. **GT was not dead, just undertested** -- original Exp 16/19b used n=78-346 with BE targets; at n=2459 with BL ground truth, correlations are 2-3x stronger (Sp=0.398 vs max |r|=0.198)
66. **Classifier-only architecture is viable** -- regressor removed, buy categories from P(avoid) + P(great_buy) only; GOOD category uses P(great_buy) >= 0.10 threshold
67. **24.9% GT coverage is a limitation** -- 76% of sets get zero-filled GT features; if coverage improves, signal may strengthen further

## Experiment 33: Theme-Level Keepa Feature Aggregates (2026-04-10)

Replace removed BE theme growth features (`theme_bayes`, `be_theme_avg_growth`) with theme-level aggregates computed from our own Keepa data. All Keepa features are already cut at `retired_date`, so no lookahead. LOO Bayesian encoding (alpha=20) prevents target leakage.

### Design

4 candidate features (LOO Bayesian encoded from per-set Keepa features):
- `theme_avg_3p_premium`: mean `3p_above_rrp_pct` within theme
- `theme_avg_retire_price`: mean `3p_price_at_retire_vs_rrp` within theme
- `theme_avg_demand`: mean `amz_review_count` within theme
- `theme_growth_x_prem`: interaction `theme_avg_3p_premium * 3p_above_rrp_pct`

All source features are pre-retirement Keepa data (cut at retired_date in Exp 31).

### Correlations with BL Target (n=2470 training sets)

| Feature | Pearson | Spearman | n |
|---------|---------|----------|---|
| `theme_avg_retire_price` | +0.141 | +0.167 | 2470 |
| `theme_avg_3p_premium` | +0.121 | +0.155 | 2470 |
| `theme_growth_x_prem` | +0.384 | +0.456 | 1703 |
| `theme_avg_demand` | +0.036 | +0.040 | 2470 |
| `theme_strong` (binary baseline) | -- | +0.095 | 2470 |
| `theme_false_pos` (binary baseline) | -- | -0.035 | 2470 |

Continuous theme features have 1.6-4.8x stronger Spearman than binary flags.

### Feature Importance (37-feature model)

All 4 theme features rank in top 13 out of 37:
- `theme_avg_retire_price`: rank #5 (gain=621)
- `theme_avg_3p_premium`: rank #10 (gain=476)
- `theme_avg_demand`: rank #12 (gain=309)
- `theme_growth_x_prem`: rank #13 (gain=286)

### LOO Correctness

Star Wars (186 sets): `theme_avg_3p_premium` range=[46.36, 46.85], 129 unique values out of 186. LOO encoding correctly produces different values per set.

### Ablation: Individual Features (P(great_buy >= 20%) AUC)

| Config | P(great_buy) AUC | Delta |
|--------|-----------------|-------|
| Baseline (33 features) | 0.7881 | -- |
| + `theme_avg_retire_price` | **0.7960** | **+0.0079** |
| + `theme_avg_3p_premium` | 0.7957 | +0.0076 |
| + `theme_avg_demand` | 0.7899 | +0.0018 |
| + `theme_growth_x_prem` | 0.7898 | +0.0017 |
| + all 4 | 0.7860 | -0.0021 |

### Subset Selection (both classifiers)

| Config | P(great_buy) AUC | P(avoid) AUC |
|--------|-----------------|--------------|
| Baseline (33 features) | 0.7881 | 0.7475 |
| + `retire_price` only | 0.7960 (+0.008) | 0.7499 (+0.002) |
| + `retire_price + 3p_premium` | 0.7915 (+0.003) | 0.7501 (+0.003) |
| **+ `retire_price + growth_x_prem`** | **0.7959 (+0.008)** | **0.7537 (+0.006)** |
| + all 4 | 0.7860 (-0.002) | 0.7466 (-0.001) |

Best combination: `theme_avg_retire_price` + `theme_growth_x_prem` (2 features).

### Key Findings

68. **Theme Keepa aggregates replace BE theme features** -- continuous LOO-encoded theme averages from Keepa data (no BE dependency) have 1.6-4.8x stronger Spearman than binary theme flags; `theme_avg_retire_price` ranks #5 by feature importance
69. **2 features beat 4** -- adding all 4 theme features dilutes signal (multicollinearity with `3p_above_rrp_pct`); best subset is `theme_avg_retire_price` + `theme_growth_x_prem`: P(great_buy) +0.008, P(avoid) +0.006
70. **Interaction captures theme-set synergy** -- `theme_growth_x_prem` (theme premium tendency * set premium) has Sp=+0.456 with target; it identifies sets with strong premiums in themes that broadly command premiums
71. **No lookahead risk** -- all source features are Keepa data cut at retired_date (Exp 31 design); LOO encoding excludes each set's own value; theme stats persisted for inference mode

### Production Integration

Features added to `KEEPA_BL_FEATURES` (26 -> 28 base, 33 -> 35 classifier with GT). Theme stats computed during training, serialized via existing `persistence.py`, used at inference via `group_mean_encode()`. Feature count: 35 total (28 Keepa+metadata + 7 GT).


## Experiment 34: New Feature Group Evaluation (2026-04-10)

Systematic evaluation of 6 feature groups (23 candidate features) against the 35-feature baseline from Exp 33. Tested regional RRP ratios, Keepa volatility, price positioning, FBM/buy box, derived interactions, and tracking users.

### Data Availability (verified in DB)

**Empty/unavailable (dead ends):** `sales_rank_json` (ALL empty), `warehouse_deals_json` (0 points), `used_price_json` (0 points), `used_like_new_json` (0 points), `collectible_json` (0 points).

### Feature Diagnostics (Spearman with BL annualized return, MI with targets)

| Feature | Group | Coverage | Spearman | MI(avoid) | MI(great_buy) | Safe? |
|---------|-------|----------|----------|-----------|---------------|-------|
| `rrp_gbp_usd_ratio` | A | 99.7% | +0.258 | 0.052 | 0.024 | SAFE |
| `rrp_eur_usd_ratio` | A | 99.4% | +0.236 | 0.029 | 0.000 | SAFE |
| `rrp_regional_cv` | A | 99.9% | -0.158 | 0.072 | 0.033 | SAFE |
| `rrp_uk_premium` | A | 92.5% | +0.267 | 0.059 | 0.028 | SAFE |
| `fba_price_range_pct` | B | 72.4% | +0.341 | 0.027 | 0.008 | SAFE |
| `amz_price_drawdown` | B | 61.2% | -0.260 | 0.021 | 0.011 | SAFE |
| `buybox_premium_avg` | D | 74.3% | +0.279 | 0.044 | 0.024 | SAFE |
| `amz_fba_spread_at_retire` | E | 63.2% | -0.267 | 0.022 | 0.017 | SAFE |
| `discount_x_tier` | E | 61.8% | -0.339 | 0.043 | 0.014 | SAFE |
| `reviews_per_dollar` | E | 79.3% | +0.287 | 0.032 | 0.006 | SAFE |
| `tracking_x_3p_premium` | F | 68.6% | **+0.513** | 0.068 | 0.035 | **LEAKY** |
| `tracking_per_dollar` | F | 74.5% | +0.344 | 0.062 | 0.023 | **LEAKY** |

### GroupKFold CV Results (9 configurations)

| Config | #Features | P(avoid) AUC | Delta | P(great_buy) AUC | Delta |
|--------|-----------|--------------|-------|-------------------|-------|
| BASELINE | 35 | 0.7990 | -- | 0.7276 | -- |
| +Group A (Regional RRP) | 39 | **0.8158** | **+0.017** | 0.7235 | -0.004 |
| +Group B (Keepa Vol) | 40 | 0.7912 | -0.008 | 0.7176 | -0.010 |
| +Group C (Price Pos) | 39 | 0.7971 | -0.002 | 0.7008 | -0.027 |
| +Group D (FBM/BB) | 39 | 0.7980 | -0.001 | 0.7251 | -0.003 |
| +Group E (Interactions) | 38 | 0.7980 | -0.001 | 0.7299 | +0.002 |
| **+SAFE_ALL** | **55** | **0.8180** | **+0.019** | **0.7370** | **+0.009** |
| +Tracking (LEAKY) | 38 | 0.8064 | +0.007 | 0.7343 | +0.007 |
| +EVERYTHING | 58 | 0.8145 | +0.016 | 0.7481 | +0.021 |

### LOFO Ablation (SAFE_ALL, removing one new feature at a time)

Removing these features hurt the most (confirming they help):
- `rrp_regional_cv`: removing drops Avoid AUC by -0.012
- `rrp_uk_premium`: removing drops GB AUC by -0.011
- `amz_fba_spread_at_retire`: removing drops GB AUC by -0.024
- `buybox_premium_avg`: removing drops both by -0.005

### Forward Selection (greedy, from baseline)

| Step | Feature Added | P(avoid) AUC | P(great_buy) AUC | Combined Delta |
|------|---------------|--------------|-------------------|----------------|
| 1 | `rrp_uk_premium` | 0.8045 (+0.006) | 0.7349 (+0.007) | +0.013 |
| 2 | `amz_fba_spread_at_retire` | 0.8095 (+0.011) | 0.7474 (+0.020) | +0.017 |
| 3 | `rrp_regional_cv` | 0.8184 (+0.019) | 0.7469 (+0.019) | +0.009 |
| 4 | `buybox_premium_avg` | 0.8156 (+0.017) | 0.7532 (+0.026) | +0.004 |
| 5 | STOP (best < 0.003 threshold) | | | |

**Selected 4 features** (35 -> 39 total):
1. `rrp_uk_premium` -- UK pricing premium deviation (LEGO prices collector sets higher in UK)
2. `amz_fba_spread_at_retire` -- 1P vs 3P gap at retirement (large gap = Amazon still stocking)
3. `rrp_regional_cv` -- cross-currency pricing variation (inconsistent = unusual set)
4. `buybox_premium_avg` -- average buy box premium vs RRP (pre-retirement market signal)

### Feature Importance (SAFE_ALL model, P(avoid) classifier)

New features ranked highly:
- `rrp_regional_cv`: **rank #2** overall (importance=141, behind only `theme_avg_retire_price`)
- `ppp_vs_theme_avg`: rank #4 (104) -- though not selected by forward selection
- `amz_fba_spread_at_retire`: rank #6 (81)
- `rrp_uk_premium`: rank #7 (70)
- `buybox_premium_avg`: rank #14 (48)

### Key Findings

72. **Regional RRP ratios are strong signals** -- `rrp_regional_cv` (CV across exchange-normalized prices) ranked #2 in feature importance; `rrp_uk_premium` (deviation from median GBP/USD) has Spearman +0.267 with BL returns. LEGO prices collector-oriented sets higher in the UK. 100% factual, no lookahead possible.
73. **1P vs 3P spread at retirement captures Amazon stocking signal** -- `amz_fba_spread_at_retire` (Amazon 1P price / 3P FBA price at retired_date) has Spearman -0.267. When Amazon is still selling at/below RRP while 3P sellers charge premium, it signals the set hasn't yet appreciated. Low spread = both channels pricing similarly = set already scarce.
74. **Buy box premium is a pre-retirement market signal** -- `buybox_premium_avg` (mean buy box price / RRP, pre-retirement) has Spearman +0.279 and MI=0.044. Higher buy box premium before retirement indicates early scarcity and collector demand.
75. **Keepa volatility and price positioning hurt individually but help in combination** -- Groups B (volatility) and C (positioning) hurt when added alone (-0.008 to -0.027 AUC) but SAFE_ALL combining all groups achieves +0.019 P(avoid) and +0.009 P(great_buy), suggesting synergistic interactions across feature groups.
76. **Tracking users are leaky but signal is modest** -- `tracking_users` (current Keepa snapshot) only adds +0.007 AUC despite being a post-retirement measurement. The modest gain suggests pre-retirement tracking_users (if scraped before retirement) would provide minimal incremental value over existing features.
77. **Forward selection finds 4 features from 20 candidates** -- greedy selection stops at 4 features (combined +0.017 P(avoid), +0.026 P(great_buy)) with no further feature adding >0.003 combined AUC. This matches the Exp 33 finding that fewer, orthogonal features beat many correlated ones.
78. **Empty Keepa data columns** -- `sales_rank_json` (would be #1 potential signal for demand velocity) has zero non-empty records. `warehouse_deals_json`, `used_price_json`, `used_like_new_json`, `collectible_json` also completely empty. These represent untapped signal sources if Keepa scraping is expanded.

### Production Integration

4 features added to `KEEPA_BL_FEATURES` (28 -> 32 base, 35 -> 39 classifier with GT):
- `rrp_uk_premium`: GBP/USD ratio - median; regional stats stored in theme_stats["regional_stats"]
- `rrp_regional_cv`: CV across exchange-normalized regional prices
- `buybox_premium_avg`: mean buy box / RRP (Keepa buy_box_json, cut at retired_date)
- `amz_fba_spread_at_retire`: amz_at_retire / 3p_at_retire ratio

Production results (2026-04-10): P(avoid) AUC=0.816 (+0.006 vs Exp 33), P(great_buy) AUC=0.778 (+0.008), Recall=98.1%.


## Experiment 35: Phase-Aware Features, Composites, and Pricing Risk (2026-04-10)

Tested 4 feature groups (14 candidates) against the 39-feature baseline from Exp 34. Focus on lifecycle phase transitions, relative signal positioning ("already priced in"), composite multi-condition signals, and demand intensity.

### Feature Diagnostics (Spearman with BL annualized return, MI with targets)

| Feature | Group | Coverage | Spearman | MI(avoid) | MI(great_buy) |
|---------|-------|----------|----------|-----------|---------------|
| `fba_prem_late_vs_early` | A:Phase | 72.5% | +0.109 | 0.005 | 0.017 |
| `spread_late_vs_early` | A:Phase | 62.2% | -0.030 | 0.000 | 0.008 |
| `fba_cv_late_vs_early` | A:Phase | 71.0% | +0.049 | 0.013 | 0.015 |
| `buybox_late_share` | A:Phase | 74.0% | -0.006 | 0.004 | 0.004 |
| `discount_deepening` | A:Phase | 57.8% | -0.186 | 0.000 | 0.008 |
| `3p_prem_vs_theme` | B:Relative | 100% | +0.192 | 0.037 | 0.030 |
| `reviews_vs_theme` | B:Relative | 100% | +0.093 | 0.033 | 0.021 |
| `buybox_vs_theme` | B:Relative | 100% | +0.040 | 0.039 | 0.030 |
| `inefficiency_x_demand` | C:Composite | 78.3% | +0.305 | 0.051 | 0.012 |
| `scarcity_pressure` | C:Composite | 67.9% | +0.288 | 0.014 | 0.031 |
| `premium_momentum` | C:Composite | 71.3% | **+0.427** | 0.038 | 0.019 |
| `theme_quality_x_premium` | C:Composite | 100% | +0.207 | 0.057 | 0.036 |
| `review_velocity` | D:Demand | 79.3% | +0.283 | 0.016 | 0.003 |
| `review_per_dollar` | D:Demand | 79.3% | +0.287 | 0.032 | 0.006 |

### Collinearity with existing `amz_discount_trend`

Phase transition features show low collinearity with existing features:
- `fba_prem_late_vs_early` vs `amz_discount_trend`: Pearson=0.317 (different channel: 3P vs 1P)
- `spread_late_vs_early` vs `amz_discount_trend`: Pearson=-0.239 (cross-channel, opposite direction)
- `fba_cv_late_vs_early` vs `amz_discount_trend`: Pearson=-0.031 (nearly independent)
- `buybox_late_share` vs `amz_discount_trend`: Pearson=0.023 (independent)

### GroupKFold CV Results (6 configurations)

| Config | #Features | P(avoid) AUC | Delta | P(great_buy) AUC | Delta |
|--------|-----------|--------------|-------|-------------------|-------|
| BASELINE | 39 | 0.8165 | -- | 0.7501 | -- |
| +Group A (Phase Trans) | 44 | 0.8199 | +0.003 | 0.7380 | -0.012 |
| +Group B (Relative Sig) | 42 | 0.8202 | +0.004 | 0.7416 | -0.009 |
| +Group C (Composites) | 43 | 0.8162 | -0.000 | 0.7494 | -0.001 |
| +Group D (Demand Int) | 41 | 0.8190 | +0.003 | 0.7420 | -0.008 |
| **+ALL_NEW (A+B+C+D)** | **53** | **0.8174** | **+0.001** | **0.7581** | **+0.008** |

### LOFO Ablation (ALL_NEW, removing one new feature at a time)

**Features that HELP (removal hurts):**
- `fba_prem_late_vs_early`: removal drops GB AUC by -0.007
- `spread_late_vs_early`: removal drops GB AUC by -0.008
- `3p_prem_vs_theme`: removal drops GB AUC by -0.012
- `reviews_vs_theme`: removal drops GB AUC by -0.009
- `buybox_vs_theme`: removal drops GB AUC by -0.011
- `scarcity_pressure`: removal drops GB AUC by -0.006
- `theme_quality_x_premium`: removal drops GB AUC by -0.008

**Features that HURT (removal helps):**
- `discount_deepening`: removal improves GB AUC by +0.004
- `premium_momentum`: removal improves avoid AUC by +0.003
- `review_per_dollar`: removal improves avoid AUC by +0.002

### Forward Selection (greedy, from 39-feature baseline)

| Step | Feature Added | P(avoid) AUC | P(great_buy) AUC | Combined Delta |
|------|---------------|--------------|-------------------|----------------|
| 1 | `theme_quality_x_premium` | 0.8182 (+0.002) | 0.7525 (+0.002) | +0.004 |
| 2 | `buybox_vs_theme` | 0.8230 (+0.007) | 0.7509 (+0.001) | +0.003 |
| 3 | `fba_prem_late_vs_early` | 0.8213 (+0.005) | 0.7593 (+0.009) | +0.007 |
| 4 | `scarcity_pressure` | 0.8231 (+0.007) | 0.7633 (+0.013) | +0.006 |
| 5 | STOP (best < 0.003 threshold) | | | |

**Selected 4 features** (39 -> 43 total):
1. `theme_quality_x_premium` [C] -- theme retire price * excess 3P premium (good theme AND above-average premium)
2. `buybox_vs_theme` [B] -- buy box premium minus LOO theme average (excess buy box = truly exceptional)
3. `fba_prem_late_vs_early` [A] -- 3P premium late half / early half (growing premium = rising demand)
4. `scarcity_pressure` [C] -- buybox_premium * (1 - spread) (high buybox + low 1P/3P gap = both channels scarce)

### Feature Importance (ALL_NEW model, P(avoid) classifier)

New features ranked in top 20:
- `reviews_vs_theme`: rank #8 (gain=63) [B:Relative]
- `buybox_late_share`: rank #10 (gain=57) [A:Phase]
- `review_velocity`: rank #11 (gain=55) [D:Demand]
- `scarcity_pressure`: rank #15 (gain=44) [C:Composite]
- `buybox_vs_theme`: rank #16 (gain=43) [B:Relative]
- `inefficiency_x_demand`: rank #17 (gain=42) [C:Composite]
- `theme_quality_x_premium`: rank #19 (gain=39) [C:Composite]

### Key Findings

79. **3P premium trajectory is a genuine new signal** -- `fba_prem_late_vs_early` (3P FBA mean in second half / first half of shelf life) adds +0.007 combined AUC. Unlike `amz_discount_trend` (Amazon 1P, Pearson=0.317), this captures 3P seller behavior evolution. Sets where 3P premium GROWS over shelf life have stronger post-retirement appreciation.
80. **"Already priced in" concept works via theme-relative signals** -- `buybox_vs_theme` (buy box premium minus LOO theme average) adds +0.003 combined AUC. A high buy box premium in a theme where premiums are normally low is more meaningful than the same premium in a theme where it's standard. 100% coverage (all sets have a theme).
81. **Composite signals capture multi-condition investment theses** -- `scarcity_pressure` (buybox * (1 - spread)) adds +0.006 combined AUC. It encodes "both channels show scarcity" -- high buy box AND low 1P/3P gap means Amazon is already sold out AND marketplace sellers are charging premium. `theme_quality_x_premium` (theme retire price * excess 3P premium) adds +0.004 combined AUC -- good theme AND above-average demand for that theme.
82. **Phase transition features are low-collinearity with existing** -- All 5 Group A features have Pearson < 0.32 with `amz_discount_trend`. The strongest (`fba_prem_late_vs_early` at 0.317) captures a different channel (3P not 1P). `fba_cv_late_vs_early` and `buybox_late_share` are nearly independent (Pearson < 0.03).
83. **Individual groups hurt P(great_buy) but ALL_NEW helps** -- Same pattern as Exp 34: groups added individually hurt GB AUC (-0.001 to -0.012) but the full combination improves it (+0.008). Features have synergistic interactions that only emerge when all groups are present.
84. **`premium_momentum` has highest Spearman (+0.427) but hurts in CV** -- Despite the strongest univariate correlation of any new feature, `premium_momentum` (3p_above_rrp_pct * fba_prem_late_vs_early) hurts the avoid classifier. This is because it's collinear with its component `3p_above_rrp_pct` (the #1 existing feature), causing overfitting. Simple products of strong features don't always help.
85. **Demand intensity features are marginal** -- `review_velocity` and `review_per_dollar` have decent Spearman (0.28) but don't survive forward selection. `review_per_dollar` was already tested in Exp 34 and remains marginal. The signal from review count is already well-captured by `amz_review_count` and `meta_demand_proxy`.

### Production Integration

4 features added to `KEEPA_BL_FEATURES` (32 -> 36 base, 39 -> 43 classifier with GT):
- `fba_prem_late_vs_early`: mean(fba_prices[50%:]) / mean(fba_prices[:50%]) -- 3P premium trajectory
- `scarcity_pressure`: buybox_premium_avg * (1 - amz_fba_spread_at_retire) -- multi-channel scarcity
- `theme_quality_x_premium`: theme_avg_retire_price * (3p_above_rrp_pct - LOO_theme_avg) -- theme quality * excess premium
- `buybox_vs_theme`: buybox_premium_avg - LOO_theme_avg(buybox_premium_avg) -- relative buy box signal

Production results (2026-04-10): P(avoid) AUC=0.820 (+0.004 vs Exp 34), P(great_buy) AUC=0.783 (+0.005), Recall=98.7%.
