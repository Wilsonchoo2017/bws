# 19b - Additional Feature Investigation

Date: 2026-04-05

## Google Trends: Pre-Retirement vs Post-Retirement Split

**Hypothesis**: GT interest while a set is on sale at LEGO.com (pre-retirement) is the real signal, not total interest.

**Result**: No. All GT features remain weak regardless of time-gating.

| Feature | n | Spearman r | p-value | Sig |
|---------|---|-----------|---------|-----|
| gt_post_mean | 277 | -0.103 | 0.087 | |
| gt_post_nonzero_pct | 277 | -0.096 | 0.112 | |
| gt_onsale_max | 277 | +0.088 | 0.142 | |
| gt_pre_max | 277 | +0.075 | 0.215 | |
| gt_all_mean | 368 | -0.044 | 0.400 | |
| gt_onsale_mean | 277 | +0.029 | 0.628 | |
| gt_pre_mean | 277 | +0.017 | 0.776 | |
| gt_pre_trend | 277 | -0.007 | 0.904 | |
| gt_post_pre_ratio | 199 | -0.004 | 0.960 | |

**Quintile analysis (on-sale GT mean):**
- Lowest GT (near zero): growth 10.9%
- Low-mid GT: growth 11.2%
- Mid-high GT: **growth 13.2%** (peak)
- Highest GT: growth 10.0% (back down)

**Conclusion**: There is a very weak inverted-U pattern -- moderate on-sale interest correlates slightly with growth, but the highest-interest sets fall back (priced-in effect). Not strong enough to use as a feature. **GT is confirmed dead for this model regardless of time-gating.**

---

## Quick Feature Ideas

### 1. Release Month/Quarter Seasonality -- NOT USEFUL
- release_quarter: r=-0.038, p=0.42 (not significant)
- Q1-Q4 growth averages are within 1.5% of each other (10.7-11.8%)
- **Verdict**: Season of release doesn't matter

### 2. Sleeper Detection -- NEGATIVE SIGNAL (unexpected)

| Feature | n | r | p | Notes |
|---------|---|---|---|-------|
| **rating_review_gap** | 706 | -0.158 | <0.0001 | Rating minus normalized review rank |
| **sleeper_score** | 706 | -0.144 | 0.0001 | Rating / log(reviews) |
| **is_sleeper** | 706 | -0.123 | 0.001 | High rating + low reviews |

**Surprise**: "Sleepers" (high rating, low reviews) grow LESS, not more. This is the opposite of the GT "hidden gem" pattern. Explanation: low reviews = niche/small sets that don't attract reseller attention. The sets that grow most have BOTH high ratings AND high reviews (mainstream appeal + quality).

**Verdict**: The `rating_x_reviews` interaction already captures this (r=+0.180). Sleeper features are just the inverse.

### 3. Theme Age/Maturity -- NOT USEFUL
- theme_age: r=+0.051, p=0.174
- 0-1yr themes: 10.7% growth, 4-7yr: 12.4% -- slight trend but not significant
- **Verdict**: Theme identity (theme_bayes) already captures this better

### 4. Multi-Currency Spread -- STRONG NEW SIGNAL

| Feature | n | r | p | Notes |
|---------|---|---|---|-------|
| **usd_vs_mean** | 706 | **-0.231** | <0.0001 | USD price vs global average |
| max_min_ratio | 706 | -0.113 | 0.003 | Max/min currency ratio |
| currency_cv | 697 | -0.107 | 0.005 | CV across 5 currencies |

**Key finding**: `usd_vs_mean` (r=-0.231) is the **3rd strongest non-leaky feature** after subtheme_loo and theme_bayes. Sets where USD price is LOW relative to the global average grow more. This is a more nuanced version of `usd_gbp_ratio` (r=-0.127).

**Interpretation**: When LEGO prices a set cheaply in the US relative to other markets, it signals either (a) aggressive US pricing strategy for high-demand sets, or (b) sets with larger global premium (non-US collectors pay more). Either way, US-cheap = more growth.

**Verdict**: `usd_vs_mean` should be added to Tier 1 features. It's the best new discovery.

### 5. Shelf Life -- NO DATA
- Only 0 sets have both year_released and year_retired in the PG-joined dataset
- Retirement year coverage is poor in BE snapshots (mostly NULL)
- **Verdict**: Need to fix data pipeline to propagate retirement dates

---

## Summary of Actionable Findings

| Feature | r | Action |
|---------|---|--------|
| **usd_vs_mean** | -0.231 | **ADD** to Tier 1 (3rd strongest non-leaky feature) |
| currency_cv | -0.107 | Consider adding (may be redundant with usd_vs_mean) |
| GT pre/post split | <0.1 | **DEAD** -- confirmed no signal regardless of time-gating |
| Sleeper detection | -0.15 | Not useful -- inverse of existing rating_x_reviews |
| Release seasonality | -0.04 | Not useful |
| Theme age | +0.05 | Not useful |
