# 19c - BrickLink Monthly Sales Investigation

Date: 2026-04-05

## Data Issue Found

BrickLink monthly sales scraping started ~Oct 2025. All 19,537 rows are from 2025-10 to 2026-04.
Since most training sets retired 2020-2024, **all sales data is post-retirement**.
There are 0 pre-retirement sales rows for the NEW condition.

## Join Fix

The original join failed because `year_retired` is NULL in both `lego_items` (6/756) and
`brickeconomy_snapshots` (0/756). The `retired_date` string field has 473/756 coverage.
Fixed join: `SPLIT_PART(bi.item_id, '-', 1) = b.set_number` + use `retired_date` for time-gating.

## Post-Retirement Sales Correlations (349 sets)

| Feature | Spearman r | p-value | Leaky? |
|---------|-----------|---------|--------|
| **premium** (avg_price/RRP) | +0.502 | <0.0001 | **YES** -- same as value_to_rrp |
| **velocity** (sold/month) | +0.369 | <0.0001 | Partially -- outcome-driven |
| **log_sold** | +0.349 | <0.0001 | Partially -- outcome-driven |
| **new/used ratio** | +0.262 | <0.0001 | Partially -- outcome-driven |
| **n_months** | +0.230 | <0.0001 | Partially |
| avg_price | +0.169 | 0.002 | YES |
| spread | +0.117 | 0.029 | Partially |

## Partial Correlation (controlling for theme)

After removing theme effects:
- log_new_sold: r=0.195, p<0.0001 -- still significant
- new/used ratio: r=0.098, p=0.036 -- barely significant

## Verdict

**All BL monthly sales features are POST-retirement and therefore leaky for training.**
They measure the OUTCOME (sets that grew more are traded more) not a CAUSE.

**For prediction of NEW sets**: these features are unavailable (no post-retirement data exists yet).

**Action**: Do NOT add to Tier 1 features. These could only be useful for:
1. Tier 2/3 as a "current momentum" signal for already-retired sets
2. As a validation metric (do our predicted winners actually trade more?)

**To get usable BL sales features**: would need to scrape monthly sales for ACTIVE sets
and build pre-retirement velocity features over time.
