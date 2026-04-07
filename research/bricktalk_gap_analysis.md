# BrickTalk vs Our ML: Gap Analysis

Source: BrickTalk Episode 40 — "10 LEGO Investing Picks Retiring July 2026"
Two experienced LEGO investors (Kevin & DG) evaluate 10 retiring sets.

## How They Evaluate Sets

For every set, they systematically check:

| Signal | How They Use It | Example |
|--------|-----------------|---------|
| **Shelf life duration** | Short (1yr) = bullish, 3yr+ = concerning | City Tower "1yr shelf life" = instant buy |
| **Amazon sales velocity** (Keepa) | Units/month, Q4 spikes, daily run rate | Piranha Plant "30k units in Q4, 600/day" |
| **Discount depth & permanence** | Never discounted = bullish; permanent 20%+ = saturated | Friends Apartments "never discounted in 15mo" = strong |
| **3P seller price vs MSRP** (Keepa FBA) | 3P prices above MSRP = proven demand pre-retirement | Fox Phoenix "lowest 3P sale $29, MSRP $23" = 20%+ premium |
| **Aftermarket seller count** | Low = less competition | Fox "12 sellers"; City Tower "only listing $340" |
| **Investor saturation** | Custom "mentions & enthusiasm" table from YouTube/community | Temple Bounty "1 mention, 0 against" = secret |
| **Comparable set performance** | Same product line retired sets | Ninjago ships: prior Destiny's Bounty $130 -> $196 |
| **Retirement timing** | July = no Black Friday = less supply flooding | "2026 unlike any year... July sets miss BF discounts" |
| **Zombie stock risk** | High velocity absorbs it; low = long overhang | Piranha Plant "100/day, zombie stock gets gobbled" |
| **Mass retail distribution** | Costco/clearance = death nail | Fountain Garden "hit Costco... destined for graveyard" |
| **eBay current price** | Already above/below MSRP pre-retirement | City Tower "$310 on eBay, retails $210" |
| **Minifigure theft risk** | No minifigs = lower return fraud risk | Piranha Plant & Rex helmet "no minifig risk" |
| **IP media trajectory** | Upcoming media = rising demand | Mario "actual minifigs coming" = theme rising |
| **Product line collectibility** | Series completionists drive demand | SW helmets as a line; 3rd Ninjago ship iteration |
| **Effective ROI from buy price** | Always from discount price, not MSRP | "Buy $35, sell $80 = double money after fees" |

## What Our ML Captures Well

- Price per part, piece count, minifig count/density
- Theme/subtheme encoding (75% of feature importance)
- Rating & reviews + cohort rankings
- Licensed theme indicator
- Multi-currency pricing (usd_vs_mean)

## Gaps: Signals They Use That We Don't

### 1. Shelf Life Duration -- EASY WIN

They use this for literally every set. Short shelf life = bullish.

- Data exists: `release_date` and `retire_date` already in `lego_items`
- We use `release_date` for quarter extraction but never compute shelf life
- **Feature:** `shelf_life_months = (retire_date - release_date).days / 30`
- **File:** `services/ml/growth/features.py`

### 2. Retirement Month/Quarter -- EASY WIN

July retirement is fundamentally different from December (no Black Friday effect).

- We have `retire_date` but don't extract month
- **Feature:** `retire_quarter` (1-4), `retires_before_q4` (binary: retire_month < 10)
- **File:** `services/ml/growth/features.py`

### 3. Amazon Sales Velocity -- MEDIUM EFFORT

Their #1 conviction signal. We extract only PRICE features from Keepa, not volume.

- Keepa data includes sales rank / estimated units but unclear if our scraper captures it
- **Feature:** `kp_monthly_units`, `kp_q4_spike_ratio`, `kp_velocity_trend`
- **Check:** Does `keepa_snapshots.amazon_price_json` contain sales rank data?

### 4. "Never Discounted" Binary -- EASY WIN (from existing Keepa data)

All 7 Keepa features together hurt T1 (R2 dropped). But a single binary might help.

- They treat "never discounted over 12+ months" as extremely bullish
- **Feature:** `never_discounted = 1 if kp_max_discount < 5% AND shelf_life > 12mo`
- Could also try: `kp_discount_permanence` = fraction of life at permanent discount

### 5. Product Line / Series Encoding -- MEDIUM EFFORT

Goes beyond theme/subtheme. "SW helmets", "Ninjago ships", "Friends modulars" are product lines.

- Could extract from subtheme + set name patterns
- **Feature:** `series_bayes` -- LOO encoding of product series growth
- Challenge: requires manual or NLP-based series identification

### 6. Investor Saturation -- NO DATA SOURCE

They track a "mentions and enthusiasm" table from YouTube. We'd need to build a scraper
for YouTube/Reddit/BrickSet forums to approximate this. Low priority.

## Key Insight

**Our model is theme-driven; their model is supply/demand-driven at the set level.**

Our theme encoding captures "Star Wars helmets generally do well" but not "this specific
helmet had a short shelf life, was never discounted, and already trades above MSRP."
The BrickTalk framework layers set-specific supply signals on top of theme identity.

## What They Use That We Proved Dead

**Google Trends** -- Kevin still uses it ("I love looking at Google Trends, Mario vs Star Wars
as baseline"). We confirmed GT is anti-signal across 7 methods. This is one area where our
ML is ahead of expert intuition.

## Implementation Priority

1. `shelf_life_months` + `retire_quarter` -- zero new data needed, add to features.py
2. `never_discounted` binary -- cherry-pick from existing Keepa data
3. Investigate Keepa sales rank/velocity data availability
4. Product line encoding (research)
5. Comparable set performance formalization (research)

## Verification

After adding features to `TIER1_FEATURES`:
1. Run `./train`, compare CV R2 vs 0.644 baseline
2. Run LOFO to confirm features survive pruning
3. Check feature importance ranking
