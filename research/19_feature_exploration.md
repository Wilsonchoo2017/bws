# 19 - Feature Exploration on 684+ Sets (via PostgreSQL)

Date: 2026-04-05

## Dataset

- 715 sets with annual_growth_pct in BE snapshots (684 with RRP > 0)
- Growth range: [0.7%, 35.4%], mean 10.9%, median 8.3%
- Data sources: BrickEconomy, BrickLink, Keepa, Google Trends

## New Features Tested

### Significant (p < 0.05) -- Added to Tier 1

| Feature | Spearman r | p-value | n | Description |
|---------|-----------|---------|---|-------------|
| subtheme_loo | +0.393 | <0.0001 | 684 | Existing, confirmed dominant |
| theme_bayes | +0.226 | <0.0001 | 684 | Existing, confirmed |
| **rating_x_reviews** | +0.180 | <0.0001 | 684 | NEW: rating * log(reviews) |
| **review_rank_in_price_tier** | +0.163 | <0.0001 | 684 | NEW: review percentile within price bracket |
| **log_reviews** | +0.162 | <0.0001 | 684 | NEW: log(review_count + 1) |
| **review_rank_in_year** | +0.157 | <0.0001 | 684 | NEW: review percentile within release year |
| **theme_growth_std** | +0.154 | 0.0001 | 684 | NEW: theme growth volatility |
| **rating_value** | +0.152 | 0.0001 | 684 | NEW: BE rating (never tested as feature) |
| **review_rank_in_quarter** | +0.150 | 0.0001 | 684 | NEW: review percentile within release quarter |
| price_per_part | -0.137 | 0.0003 | 676 | Existing, confirmed |
| **dist_cv** | +0.131 | 0.0008 | 655 | NEW: distribution coefficient of variation |
| usd_gbp_ratio | -0.127 | 0.0011 | 667 | Existing, confirmed |
| theme_size | -0.124 | 0.0012 | 684 | Existing, confirmed |
| **mfig_value_to_rrp** | +0.145 | 0.0254 | 236 | NEW: minifig value / RRP (low coverage) |
| **has_designer** | +0.094 | 0.014 | 684 | NEW: named designer flag |
| is_licensed | +0.091 | 0.017 | 684 | Existing, confirmed |

### Not Significant (dropped or weak)

| Feature | Spearman r | p-value | Notes |
|---------|-----------|---------|-------|
| review_rank_in_theme | +0.046 | 0.228 | Not useful -- theme_bayes already captures this |
| minifig_density | +0.047 | 0.224 | Existing, weak |
| sub_size | -0.045 | 0.241 | Existing, weak |
| mfigs | +0.039 | 0.313 | Existing, weak |
| log_rrp | -0.035 | 0.357 | Existing, weak |
| price_tier | -0.031 | 0.420 | Existing, weak |
| log_parts | +0.006 | 0.872 | Existing, near zero |

### Confirmed Non-Signals (revalidated with more data)

| Source | Feature | r | n | Finding |
|--------|---------|---|---|---------|
| Google Trends | gt_mean | -0.052 | 346 | Still anti-signal, confirmed |
| Google Trends | gt_last_quarter | -0.098 | 346 | Still anti-signal, confirmed |
| Keepa | tracking_users | +0.057 | 460 | Not significant (p=0.22) |
| Keepa | log_tracking | +0.057 | 460 | Not significant (p=0.13) |
| Minifigs | unique_mfigs | +0.076 | 386 | Not significant |
| Minifigs | mfigs_per_dollar | -0.008 | 383 | Near zero |

### Leaky Features (excluded from training)

| Feature | r | Notes |
|---------|---|-------|
| growth_rank_in_year | +0.984 | LOO-encoded target percentile (circular) |
| growth_rank_in_price_tier | +0.980 | Same issue |
| growth_rank_in_quarter | +0.977 | Same issue |
| growth_rank_in_theme | +0.846 | Same issue |
| value_to_rrp | +0.681 | Uses current market value |

## Cohort Rankings Implemented

5 cohort dimensions for review rankings (non-leaky):
1. **Release year** -- sets from the same year
2. **Release quarter** -- 3-month buckets within year
3. **Price tier** -- 8 price brackets ($0-15, $15-30, ..., $500+)
4. **Theme** -- same LEGO theme
5. **Retirement year** -- sets retiring same year (low coverage)

Growth rankings computed for analysis but excluded from training (leaky).

## Feature Selection

MI-based selection with redundancy filtering (|corr| > 0.90):
- Input: 24 candidate features
- Output: 18 selected features
- Dropped: low-MI features (log_parts, price_tier, etc.)

## Architecture Changes

1. Added `services/ml/growth/feature_selection.py` -- MI + redundancy filter
2. Added `services/ml/pg_queries.py` -- PG-compatible data loading
3. Updated `./train` to support `--pg` flag for PostgreSQL training
4. Updated `services/scoring/growth_provider.py` -- production loads from disk only
5. Growth rank features added to `CIRCULAR_FEATURES` in evaluation.py

## Next Steps

- Run `./train --pg` with new features and compare to baseline (R2=0.479 on 322 sets)
- Investigate BrickLink monthly sales join issue (0 pre-retirement rows matched)
- Add retirement_year cohort once year_retired coverage improves
