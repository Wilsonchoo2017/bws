# Feature Engineering & Model Experiments

## 05 - Intrinsics-Only Model (266 sets, zero leakage)

**Dataset**: 266 sets with BE `value_new` + `rrp_usd` + `annual_growth_pct` + set metadata. No current prices, no BrickLink, no candlestick used as features. Zero leakage. 36 unique themes.

### Model Performance

**Classification** (>=10% growth, 5-fold CV, 10 repeats):
| Model | Accuracy | AUC |
|-------|----------|-----|
| **GBM** | **0.706** | **0.767** |
| RF | 0.639 | 0.684 |
| Logistic | 0.606 | 0.635 |
| Baseline | 0.549 | - |

**Regression** (5-fold CV, 10 repeats):
| Model | R2 | MAE |
|-------|-----|-----|
| **GBM** | **0.154** | **5.07%** |
| RF | 0.123 | 5.22% |
| Ridge | -0.057 | 5.91% |

**LOO Regression**: R2=0.227, MAE=4.97%, Correlation=0.478

### Feature Importance (Permutation)

| Feature | Importance | Interpretation |
|---------|-----------|----------------|
| theme_loo_growth | 0.499 | Theme-level growth (LOO-encoded) dominates -- theme is the #1 predictor |
| theme_size | 0.090 | Number of sets in theme -- smaller themes grow faster |
| log_rrp | 0.065 | RRP matters -- but nonlinear |
| subtheme_avg_growth_pct | 0.062 | Subtheme momentum |
| be_review_count | 0.054 | Number of reviews |
| log_parts | 0.052 | Parts count |
| price_per_part | 0.046 | Value density |
| minifig_density | 0.041 | Minifig-to-parts ratio |

### Per-Theme Performance

Strong within-theme prediction (model learns theme-specific patterns):
| Theme | n | MAE | Correlation |
|-------|---|-----|-------------|
| Star Wars | 44 | 2.6% | 0.67 |
| Super Heroes | 27 | 5.1% | 0.79 |
| Minecraft | 13 | 7.1% | 0.75 |
| Monkie Kid | 11 | 3.5% | 0.72 |

Weak themes (model can't differentiate within):
| Theme | n | MAE | Correlation |
|-------|---|-----|-------------|
| DUPLO | 19 | 6.0% | -0.19 |
| Creator | 16 | 5.8% | -0.03 |
| BrickHeadz | 11 | 5.3% | -0.81 |

### Key Insights

1. **AUC=0.767 from set DNA alone** is surprisingly strong. Theme identity is by far the dominant signal (50% of importance), but within-theme features (parts, price, minifig density) add real value.

2. **The model is conservative** -- biggest errors are underpredictions of breakout sets (BD-1, Nano Gauntlet, Axolotl House). These are sets with exceptional collector/cultural appeal that intrinsics can't capture.

3. **Overpredictions cluster in themes with high averages** but the specific set underperforms (e.g., Ministry of Magic in Harry Potter theme).

4. **Comparison across experiments:**
| Experiment | Data | AUC | R2 | Notes |
|-----------|------|-----|-----|-------|
| 02 (leaky) | 211 sets | 0.857 | 0.626 | BL prices leak target |
| 03 (partial leak) | 211 sets | 0.748 | 0.433 | BL market features still leaky |
| 04 (temporal) | 48 sets | 0.668 | 0.248 | Early candlestick, small sample |
| **05 (intrinsics)** | **266 sets** | **0.767** | **0.227** | **Zero leakage, largest dataset** |

5. **Intrinsics beat temporal** because 266 >> 48 samples, even though temporal features have more signal per feature. Data quantity > feature quality at this scale.

### Next Steps
- Add Keepa features to intrinsics model -- DONE in 06

---

## 06 - Combined Model: Intrinsics + Keepa (113 sets)

**Dataset**: 113 sets with BE + Keepa data (RRP filter reduced from 178). Google Trends had only 4 overlapping sets so was excluded.

### Keepa adds massive signal

**Feature set comparison** (GBM, 5-fold CV, 10 repeats):
| Feature Set | AUC | R2 | MAE |
|-------------|-----|-----|-----|
| Intrinsics only (17 feat) | 0.688 | -0.107 | 6.09% |
| **Intrinsics + Keepa (24 feat)** | **0.744** | **0.375** | **4.44%** |

Keepa features pushed R2 from negative to **0.375** -- intrinsics alone on 113 sets can't even beat the mean, but adding Keepa unlocks real predictive power.

### Best Model Performance

**LOO Regression** (GBM): R2=**0.511**, MAE=**4.21%**, Correlation=**0.715**

This is our best honest model yet. Comparison:

| Experiment | n | AUC | LOO R2 | LOO Corr | Notes |
|-----------|---|-----|--------|----------|-------|
| 05 intrinsics | 266 | 0.767 | 0.227 | 0.478 | More data, fewer features |
| **06 combined** | **113** | **0.744** | **0.511** | **0.715** | **Fewer sets but richer features** |
| 04 temporal | 48 | 0.668 | 0.248 | 0.505 | Small sample |

### Top Features

| Feature | Perm Importance | Correlation | Type |
|---------|-----------------|-------------|------|
| **keepa_discount_pct** | **1.166** | **-0.610** | KEEPA |
| log_keepa_tracking | 0.134 | +0.172 | KEEPA |
| be_review_count | 0.094 | +0.153 | intrinsic |
| log_parts | 0.073 | +0.088 | intrinsic |
| usd_gbp_ratio | 0.046 | -0.257 | intrinsic |

**`keepa_discount_pct` is the single most powerful predictor** (perm importance 1.17, r=-0.61). Sets that Amazon discounts heavily appreciate LESS. This makes intuitive sense:
- Heavy discounts = Amazon trying to clear stock = low demand
- Minimal/no discount = strong retail demand = scarcity after retirement

**`log_keepa_tracking`** (tracking users watching the price) is a direct demand proxy.

### Error Analysis by Growth Bucket

| Bucket | n | MAE |
|--------|---|-----|
| 0-5% | 22 | 3.5% |
| 5-8% | 37 | 3.2% |
| 8-10% | 8 | 1.9% |
| 10-12% | 9 | 3.6% |
| 12-15% | 10 | 4.5% |
| 15-20% | 10 | 6.1% |
| 20%+ | 17 | 7.5% |

The model is most accurate for moderate growers (5-12%) and struggles most with high performers (20%+).

### Key Insight: Amazon Discount is the Best Signal

The Keepa Amazon discount percentage is the best single predictor we've found across all experiments. It's:
1. **Not leaky** -- the Amazon discount exists BEFORE retirement
2. **Strong signal** (r=-0.61)
3. **Intuitive** -- Amazon discounting reflects demand/supply dynamics
4. **Actionable** -- you can check Amazon price before buying

### LEAKAGE CONFIRMED

**All 113 sets have $0 Amazon price.** Amazon is out of stock on every one. `current_new_cents` is the **third-party seller price**, not an Amazon retail discount. The "discount" is actually a post-retirement markup:
- Nano Gauntlet: 3P price 3.4x RRP ("discount" = -241%)
- BD-1: 3P price 2.4x RRP ("discount" = -138%)

`keepa_discount_pct` correlates at 0.61 with growth because it IS the growth (3P markup = appreciation). Same leakage as `value_to_rrp` from experiment 02.

**Clean Keepa retest** (removing all price-based features, keeping only tracking_users, reviews, rating):
| Feature Set | LOO R2 | LOO Corr |
|-------------|--------|----------|
| Intrinsics only | 0.083 | 0.325 |
| Intrinsics + Clean Keepa | -0.056 | 0.173 |

Clean Keepa features add **zero signal** -- they actually degrade the model. The tracking users, review count, and rating are too noisy to predict growth on this sample.

**Conclusion**: Experiment 06's R2=0.511 was entirely driven by leakage. The real performance on 113 sets is R2~0.08, consistent with experiment 05's intrinsics-only results scaled to a smaller sample.

### Next Steps
- Extract pre-OOS Amazon signals from Keepa timeline -- DONE in 07

---

## 07 - Keepa Timeline Model (80 sets, Amazon price history)

**Key insight from user**: When Amazon goes out of stock (OOS), the buy box shifts to third-party FBA sellers -- this is the free market. Keepa has the full historical timeline showing when Amazon had stock, their pricing behavior, and the transition to 3P.

### Feature Extraction from Keepa Timeline

**Pre-OOS (clean, available before retirement):**
| Feature | Correlation | Description |
|---------|-------------|-------------|
| below_rrp_pct | -0.363 | % of time Amazon priced below RRP |
| price_trend | +0.344 | Price direction while Amazon had stock |
| max_discount | -0.131 | Deepest Amazon discount |
| months_in_stock | -0.136 | How long Amazon kept stock |

**At-OOS (borderline -- measured at retirement moment):**
| Feature | Correlation | Description |
|---------|-------------|-------------|
| bb_premium_at_oos | +0.486 | Buy box premium when Amazon runs out |
| fba_premium_at_oos | +0.331 | 3P FBA premium at OOS |

### Feature Set Ablation (80 sets)

| Feature Set | CV AUC | LOO R2 | LOO Corr |
|-------------|--------|--------|----------|
| A: Intrinsics only | **0.786** | 0.075 | 0.318 |
| B: Intrinsics + Pre-OOS | 0.676 | -0.082 | 0.281 |
| C: B + Keepa demand | 0.666 | -0.032 | 0.310 |
| D: Intrinsics + Pre-OOS + At-OOS | 0.722 | **0.087** | **0.394** |
| E: Everything | 0.741 | 0.039 | 0.364 |

### Key Findings

1. **Pre-OOS Amazon features DEGRADE the model** on 80 sets. Going from intrinsics-only (AUC 0.786) to intrinsics + Pre-OOS (AUC 0.676). The correlations are there (r=-0.36 for below_rrp_pct) but with 80 samples and 19 features, overfitting dominates.

2. **At-OOS features (bb_premium) help** -- adding them recovers performance (D: LOO corr 0.394 vs A: 0.318). The buy box premium at the moment Amazon runs out is a legitimate "free market price" signal.

3. **Intrinsics-only remains strongest on AUC** (0.786) because with small n, fewer features = less overfitting.

4. **The 80-set sample is too small** for 19+ features. Pre-OOS features have signal (correlations are real) but can't be leveraged with this dataset size.

### Honest Assessment: Where We Stand

| Experiment | n | Best LOO R2 | Best AUC | Feature Type |
|-----------|---|-------------|----------|-------------|
| 05 Intrinsics | 266 | 0.227 | **0.767** | Set DNA |
| 04 Temporal | 48 | 0.248 | 0.668 | Early candlestick |
| 07 Keepa timeline | 80 | 0.087 | 0.786 | Amazon behavior |

**Experiment 05 (intrinsics, n=266) remains our best production model.** It has the most data, simplest features, and best AUC. The Keepa timeline features have real signal but need 200+ sets to be useful.

### What Would Actually Improve the Model
1. **More data** -- scrape BrickEconomy for 500+ retired sets
2. **Pre-retirement Keepa scraping** -- capture Amazon discount WHILE set is still in stock, not after
3. **Theme-specific models** -- Star Wars, Harry Potter, NINJAGO have enough sets for dedicated models
4. **The buy box premium at OOS** (bb_premium_at_oos, r=+0.49) is the strongest single signal we've found that isn't clearly leaky, but needs validation on more data

---

## 08 - Combined Feature Sets + Theme-Specific (157 sets)

Tested combining intrinsics with candlestick temporal features and Keepa timeline features. Also tested Star Wars-specific model.

### Results

**Full dataset (157 sets, intrinsics only):**
- CV AUC=0.798, R2=0.361, MAE=4.12%
- **LOO R2=0.432, Corr=0.662, MAE=3.88%**
- This is our best result yet on a clean dataset

**Candlestick subset (41 sets):**
| Feature Set | LOO R2 | LOO Corr |
|-------------|--------|----------|
| Intrinsics only | 0.197 | 0.464 |
| Temporal only | -0.558 | -0.173 |
| Intrinsics + Temporal | -0.112 | 0.253 |

Adding temporal features **hurts** on 41 sets -- overfitting with 18 features on 41 samples.

**Keepa timeline subset (22 sets):**
| Feature Set | LOO R2 | LOO Corr |
|-------------|--------|----------|
| Intrinsics only | 0.228 | 0.538 |
| Keepa timeline only | -0.252 | 0.020 |
| Intrinsics + Keepa | 0.135 | 0.491 |

Same pattern -- Keepa features alone are useless, and adding them to intrinsics degrades slightly.

**Star Wars only (43 sets):**
- LOO R2=-0.395, Corr=-0.170
- Theme-specific model fails without theme features. Within Star Wars, intrinsics can't differentiate winners from losers.

### Key Conclusions

1. **Intrinsics-only model on the full dataset is definitively the best** (LOO R2=0.432, Corr=0.662). This is a strong result.

2. **Additional data sources degrade performance** on their smaller subsets due to overfitting. The marginal signal from temporal/Keepa features doesn't compensate for the sample size loss.

3. **Theme-specific models don't work** with current data sizes. 43 Star Wars sets isn't enough to learn within-theme patterns without the theme feature.

4. **`theme_loo_growth` dominates** (perm importance 1.025) -- theme identity is overwhelmingly the strongest predictor. `theme_size` is second (0.232).

5. **The path to improvement is more data**, not more features.

### Data Inventory Script

Created `research/check_data.py` for quick data volume checks.

---

## Future Features to Test (need more data)

Features we've identified as promising but can't test yet due to insufficient data coverage.

### Google Trends (currently 17 sets, need 100+)
- **Average search interest** (r=+0.20 on 17 sets) -- sustained demand signal
- **Interest trend near retirement** -- rising/falling search buzz before EOL
- **Interest shape** -- spike-and-fade vs steady interest (from 223-point weekly time series)
- **Interest relative to theme baseline** -- does this set get more searches than typical for its theme?
- **Peak timing** -- when did peak interest occur relative to retirement date?

Priority: HIGH. This is likely the missing "cultural relevance" signal that could predict breakout sets (BD-1, Nano Gauntlet) that intrinsics always underpredict.

### Amazon Sellout Dynamics (currently 49 sets, need 100+)
- **Sellout speed** -- how fast did Amazon go OOS after first discount? (fast = high demand)
- **Pre-OOS price trajectory** -- was Amazon raising or lowering price before stock ran out?
- **Buy box premium at OOS** (r=+0.49 on 49 sets) -- free market valuation at retirement
- **3P seller entry speed** -- how quickly did FBA sellers appear after Amazon OOS?

Priority: MEDIUM. Strong signal from bb_premium_at_oos but borderline leaky.

### Cohort-Relative Traction (need richer activity data)
- **Relative sales velocity** -- within sets released same year/month, which sold faster?
- **Relative Google Trends interest** -- which sets got disproportionate attention?
- **Ranking within theme+year** -- best-in-class within its cohort

Priority: HIGH. User's insight -- relative performance within a cohort removes time-period effects.

### External Data (would need new scrapers)
- **Reddit mention frequency** -- r/lego, r/legomarket buzz
- **YouTube review view counts** -- popular reviews = popular set
- **BrickSet want-list count** -- direct collector demand signal
- **Instagram hashtag count** -- social media traction

Priority: LOW (requires new infrastructure).

---

## 09 - Enriched Intrinsics: Theme-relative + Cohort + Interactions (157 sets)

Tested 19 new engineered features on top of the 12 baseline intrinsics.

### Ablation Results

| Config | Feats | LOO R2 | LOO Corr | AUC |
|--------|-------|--------|----------|-----|
| **A: Baseline** | **12** | **0.432** | **0.662** | **0.798** |
| B: + Theme-relative | 18 | 0.388 | 0.624 | 0.763 |
| C: + Cohort ranking | 19 | 0.391 | 0.627 | 0.763 |
| D: + Interactions | 16 | 0.436 | 0.666 | 0.794 |
| E: + Category proxy | 14 | **0.444** | **0.675** | 0.783 |
| F: + Theme-rel + Cohort | 25 | 0.394 | 0.630 | 0.740 |
| G: ALL 31 features | 31 | 0.357 | 0.599 | 0.720 |

### Key Findings

1. **Baseline (12 features) remains the best overall model.** Adding features hurts due to overfitting on 157 samples. More features = worse.

2. **Category proxy (E) slightly improved R2** (0.432 -> 0.444) but at the cost of AUC (0.798 -> 0.783). The `collector_score` and `value_density` features add marginal regression signal but don't improve classification.

3. **Interactions (D) are neutral** -- nearly identical to baseline. The GBM can already capture these interactions at depth=3.

4. **Theme-relative and cohort features hurt** -- they add noise on this sample size. The z-scores and rankings within small groups (e.g., 5 SPEED CHAMPIONS sets) are unstable.

5. **Breakout sets remain unpredictable** -- none of the new features helped predict BD-1, Venom, Nano Gauntlet, etc. The model still underpredicts all top performers by 10-20 percentage points.

6. **New feature correlations are weak**: best is `rating_rank_cohort` at r=+0.22. None reach the r>0.3 threshold for strong signal.

### Conclusion

With 157 sets, the 12-feature baseline is at or near optimal complexity. Adding features only adds noise. The path to improvement is:
1. **More data** (500+ sets would allow richer features without overfitting)
2. **Google Trends** (cultural relevance signal to catch breakout sets)
3. **Pre-retirement Keepa** (Amazon demand dynamics)

---

## 10 - Sales Trend + Subtheme + BrickLink Monthly Sales (157 sets)

Tested untapped data: BE sales_trend_json (monthly BrickLink sales counts), subtheme LOO growth, and BrickLink monthly sales table.

### New Feature Correlations

| Feature | Correlation | Source | Leaky? |
|---------|-------------|--------|--------|
| st_avg_sales | +0.448 | BE sales trend | YES - current sales volume |
| st_n_months | -0.431 | BE sales trend | YES - proxy for set age |
| bl_avg_monthly_sold | +0.342 | BL monthly | YES - current sales |
| bl_price_trend | +0.317 | BL monthly | Partially - price direction |
| subtheme_loo_growth | +0.288 | Subtheme | Clean |

### Ablation Results

| Config | AUC | LOO R2 | LOO Corr |
|--------|-----|--------|----------|
| A: Baseline | 0.798 | **0.432** | **0.662** |
| B: + Sales Trend | 0.786 | 0.442 | 0.665 |
| C: + Subtheme | 0.802 | 0.263 | 0.513 |
| D: + BL Monthly | 0.733 | 0.354 | 0.595 |
| F: All new | 0.753 | 0.429 | 0.658 |

### Key Findings

1. **Sales features have strong correlations but are largely leaky.** `st_avg_sales` (r=+0.45) reflects current popularity, not a pre-retirement signal.

2. **`st_avg_sales` became the top feature** in permutation importance (0.269) when included, surpassing `theme_loo_growth`. But it's measuring post-retirement demand.

3. **Sales trend (B) marginally improved R2** (0.432 -> 0.442) and helped 7/15 breakout sets (notably Fast & Furious +10.6->+21.5).

4. **Subtheme hurt** -- LOO growth on small groups overfits.

5. **Baseline remains best overall.** Delta R2 = -0.003.

### Leakage Assessment

The sales/BL features are measured TODAY, reflecting current market state. To be useful, we'd need historical sales data from BEFORE retirement -- e.g., "how fast was this set selling on BrickLink in its first year on market?"

### Research Status (after 10 experiments)

Best model before tuning: 12-feature intrinsics, AUC=0.798, LOO R2=0.432 (157 sets).

---
