# Research Findings: LEGO Set Investment Return Prediction

## 01 - Exploratory Data Analysis (38 sets, all 3 sources)

**Dataset**: 38 sets with complete BrickEconomy + BrickLink + Keepa data. All from 2022. 5 themes (mostly Star Wars 17, NINJAGO 18).

### Key Findings

**Growth Distribution**
- Mean 10.5%, median 7.0%, std 7.4%
- 37% of sets grow >10% annually (our "good investment" threshold)
- Top performers: Nano Gauntlet (31.3%), Venom (30.4%), BD-1 (30.4%)

**Top Predictive Features** (correlation with annual growth):
| Feature | Correlation | Interpretation |
|---------|-------------|----------------|
| keepa_discount_pct | -0.584 | Sets with bigger Amazon discounts grow LESS. Makes sense: heavily discounted = less scarcity |
| bl_supply_demand | -0.309 | Lower BrickLink supply-to-demand ratio = more growth. Scarcity drives appreciation |
| bl_current_new_qty | -0.270 | Fewer current listings = more growth. Same scarcity signal |
| dist_cv | +0.225 | Higher price distribution variance = more growth. Volatile pricing = opportunity |

**Feature Importance** (GBM regression):
- keepa_discount_pct dominates at 52% importance
- parts_count at 14.5%
- bl_supply_demand at 8.6%
- Everything else < 5%

**Model Performance** (LOO CV, n=38):
- Classification accuracy: 65.8% vs 63.2% baseline (barely above chance)
- R2: NaN (LOO with single samples, expected)
- Conclusion: 38 samples is too small for reliable modeling

**Theme Analysis**:
- NINJAGO: 56% good investments, avg 12.7% growth
- Star Wars: 18% good investments, avg 8.7% growth
- Avatar: 1 set, 14.8% (too small to conclude)

**Price Tier Analysis**:
- Cheapest (<$20) and $100-200 tiers perform best (67% good investment rate)
- Mid-range ($20-100) performs worst (~29% good rate)

### Limitations
- Only 38 samples, all from 2022
- 5 themes only (selection bias from what's in our database)
- Single snapshot in time (no temporal validation)

### Next Steps
- Expand to 204 sets (BE + BL, drop Keepa requirement) -- DONE in 02

---

## 02 - Expanded Model (211 sets, BE + BL)

**Dataset**: 211 sets with BrickEconomy + BrickLink data (dropped Keepa requirement). 25 features with >=50% coverage.

### Model Performance

**Classification** (5-fold CV, 10 repeats):
| Model | Accuracy | AUC |
|-------|----------|-----|
| Logistic Regression | 0.792 | 0.842 |
| Random Forest | 0.813 | **0.857** |
| Gradient Boosting | 0.822 | 0.856 |
| Baseline (majority) | 0.673 | - |

**Regression** (5-fold CV, 10 repeats):
| Model | R2 | MAE |
|-------|-----|-----|
| Ridge | 0.289 | 3.81% |
| Random Forest | **0.626** | **2.81%** |
| Gradient Boosting | 0.619 | 2.81% |

### Top Predictive Features

**Correlations with annual growth:**
| Feature | Correlation | Interpretation |
|---------|-------------|----------------|
| value_to_rrp | +0.568 | Current value vs RRP. Essentially the target encoded differently - sets that already appreciated show high growth. **Leakage risk** - this is measured at scrape time, not at purchase time. |
| theme_avg_growth | +0.411 | Theme-level average growth. Strong theme signal. |
| new_used_ratio | +0.355 | Higher new/used price ratio = more growth. Collector demand for sealed sets. |
| bl_6m_used_sold | +0.351 | More used sales = more growth. Active secondary market = appreciation. |
| bl_6m_used_qty | +0.342 | Same signal as above. |
| bl_6m_new_sold | +0.289 | More new sales = more growth. Demand signal. |
| rating_value | +0.285 | Higher BE rating = more growth. Quality matters. |

**GBM Feature Importance:**
- `value_to_rrp` dominates (51% cls, 55% reg) -- **likely leakage, needs investigation**
- `bl_6m_new_sold`, `bl_6m_new_avg`, `theme_avg_growth` are the next tier

### Key Observations

1. **Data leakage concern**: `value_to_rrp` is the #1 feature but it's essentially a re-encoding of the target. Current market value / RRP correlates with growth because sets that grew a lot have high value-to-RRP ratios. In a real prediction scenario, we wouldn't know the current value at decision time.

2. **Even without leaky features, AUC ~0.85 is promising**. The BrickLink market signals (sold quantities, price spread) and theme-level features carry real predictive power.

3. **Error analysis**: 17% misclassification rate. Most false negatives are borderline (10-15% growth). Most false positives are also borderline (6-10%). The model struggles most at the boundary.

4. **Regression MAE of 2.81%** means predictions are typically within 3 percentage points of actual growth.

### Critical Issue: Feature Leakage

`value_to_rrp` is measured AFTER appreciation has occurred. For a useful model, we need features measurable BEFORE or AT retirement time:
- Set characteristics (parts, theme, price, minifigs)
- BrickLink market activity (listing counts, sales velocity)
- Theme/subtheme growth rates
- Amazon pricing (if available)

### Next Steps
- Remove leaky features and retrain -- DONE in 03

---

## 03 - No-Leakage Model (211 sets, clean features only)

Removed `value_to_rrp`, `new_used_ratio`, and `theme_avg_growth` (target leakage in CV). 27 clean features remaining.

### Model Performance (no leakage)

**Classification** (5-fold CV, 10 repeats):
| Model | Accuracy | AUC |
|-------|----------|-----|
| Logistic | 0.724 | 0.745 |
| **Random Forest** | **0.721** | **0.748** |
| GBM | 0.704 | 0.730 |
| Baseline | 0.673 | - |

**Regression** (5-fold CV, 10 repeats):
| Model | R2 | MAE |
|-------|-----|-----|
| Ridge | 0.139 | 4.25% |
| RF | 0.403 | 3.62% |
| **GBM** | **0.433** | **3.43%** |

### Clean Feature Importance (Permutation)

| Feature | Perm Importance | Interpretation |
|---------|-----------------|----------------|
| bl_6m_new_avg | 0.104 | Average BrickLink new sale price - highest single predictor |
| bl_cur_new_lots | 0.060 | Current listing count - scarcity signal |
| price_tier | 0.026 | RRP price band matters |
| bl_cur_new_qty | 0.026 | Available inventory |
| log_bl_activity | 0.020 | Total market activity (new + used sales) |
| dist_cv | 0.017 | Price distribution spread |
| bl_price_spread | 0.014 | Min/max price gap |

### Error Analysis by Growth Bucket

The model's weakness is clearly at the **decision boundary (8-15%)**:
- 0-5% growth: 91% accuracy (easy to identify losers)
- 5-8%: 85% accuracy
- 8-10%: 71% (near threshold, hard)
- **10-12%: 25% accuracy** (biggest weakness - marginal winners misclassified)
- **12-15%: 28% accuracy** (same problem)
- 15-20%: 46%
- 20%+: 83% (easy to identify big winners)

**Key insight**: The model is good at extremes but struggles with borderline cases. This suggests a 3-class model (poor/marginal/strong) or a higher threshold (15%) might work better.

### Conclusions

1. **The signal is real** - even without leaky features, AUC=0.748 significantly beats random (0.5) and majority baseline (0.673).
2. **BrickLink market features are the strongest predictors** - average sale price, listing counts, and market activity.
3. **Set intrinsics (parts, price tier) add signal** but are weaker than market data.
4. **R2=0.433 for regression** - the model explains ~43% of growth variance. MAE of 3.4% means predictions are typically within 3.4 percentage points.
5. **Boundary problem** - model struggles most at 10-15% growth (the decision boundary). Consider adjusting threshold or using a 3-class approach.

### Next Steps
- Use historical candlestick data instead of current-day BrickLink snapshots -- DONE in 04

---

## 04 - Temporal Model (42 sets, candlestick-based, no leakage)

**Critical insight from user**: BrickLink data is today's snapshot -- it already reflects appreciation. Using it to predict growth is circular. The BrickEconomy candlestick data has the actual monthly price history, allowing us to go back in time.

**Setup**: Features from first 6 months of price action + set intrinsics. Target: actual 12m/24m returns computed from later candlestick data. Only 42 sets have sufficient history (12+ months).

### Return Distributions (from candlestick)

| Horizon | Mean | Median | Std | % Positive | % >20% |
|---------|------|--------|-----|------------|--------|
| 12m | 26.0% | 23.0% | 26.3% | 88% | 55% |
| 24m | 60.9% | 48.8% | 46.3% | 98% | 88% |
| 36m | 70.7% | 56.8% | 61.6% | 95% | 78% |

LEGO sets overwhelmingly appreciate. 88% positive at 12m, 98% at 24m. The question isn't IF they appreciate, but HOW MUCH.

### Model Performance (12m prediction, LOO CV)

**Regression**:
| Model | R2 | MAE | Correlation |
|-------|-----|-----|-------------|
| GBM | **0.123** | **16.4%** | **0.382** |
| RF | 0.039 | 17.7% | 0.250 |
| Ridge | -0.001 | 19.1% | 0.313 |

**Classification** (>20% = good, LOO CV):
| Model | Accuracy | AUC |
|-------|----------|-----|
| RF | **0.667** | **0.668** |
| GBM | 0.619 | 0.632 |
| Logistic | 0.571 | 0.664 |

### Top Predictive Features (temporal, no leakage)

| Feature | Correlation | Perm Importance | Interpretation |
|---------|-------------|-----------------|----------------|
| max_discount | -0.491 | 0.123 | Sets that dip below RRP early = worse future returns |
| has_minifigs | -0.477 | 0.000 | Surprising: sets WITHOUT minifigs do better? Small sample bias likely |
| avg_mom | +0.461 | 0.095 | Strong month-over-month price increases early = continued growth |
| early_return | +0.431 | 0.147 | First 6 months return strongly predicts 12m return. Momentum is real. |
| norm_slope | +0.396 | 0.024 | Steeper early price slope = better future returns |
| avg_vs_rrp | +0.370 | 0.009 | Trading above RRP early = good sign |

### Key Insights

1. **Early momentum predicts future returns.** Sets that appreciate in the first 6 months continue appreciating. This is the strongest signal.

2. **Discount below RRP is a bad sign.** Sets that trade below RRP early have significantly worse 12m returns. Counter to "buy the dip" intuition.

3. **The model struggles with outliers.** Darth Vader Bust (+130% actual vs +41% predicted) and Emmet's Triple-Decker (-14% actual vs +38% predicted) are badly missed. With 42 samples, extreme cases are impossible to learn.

4. **R2 = 0.12 is honest.** Previous models showed R2=0.43+ but were using leaky features. The true predictive power from temporal features is modest -- we can explain ~12% of return variance from early price action and set characteristics.

5. **Classification AUC=0.67** is above random (0.5) but far from the 0.85 we saw with leaky features. This is the real signal strength.

6. **24m predictions are slightly better** (Ridge R2=0.20, Corr=0.48). Longer horizons may be easier to predict because short-term noise averages out.

### Honest Assessment

The temporal model is significantly weaker than the cross-sectional one (exp 02-03), which confirms those models were partially leaky. The real predictive power from features available at decision time is:
- **Modest but real** (AUC 0.67, R2 0.12)
- **Driven by momentum** (early price trajectory is the top signal)
- **Limited by sample size** (42 sets, mostly 2019 cohort)

### Next Steps
- Need more historical data (scrape more retired sets from BrickEconomy)
- Build intrinsics-only model on larger dataset -- DONE in 05

---

