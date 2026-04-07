# BrickTalk vs Our ML: Gap Analysis 2

Source: BrickTalk Episode 39 — "10 Retiring LEGO Investment Picks for 2026 Good Set or Bad Set"
Same two hosts (Kevin & DG) evaluate 10 sets: AT-TE, Gringotts, Fast & Furious GTR, Sorting Hat, Optimus Prime, Executor SSD, Mona Lisa, Great Pyramid of Giza, Dark Falcon (teased), Jabba's Sail Barge, NASA Perseverance.

This document captures **new signals not already identified in bricktalk_gap_analysis.md**.

---

## New Signals Identified

### 1. Minifigure Value-to-RRP Ratio as a Primary Signal

We already have `mfig_value_to_rrp` in our feature set, but the BrickTalk hosts use it far more aggressively and with a clearer threshold:

- AT-TE: "$45 in minifig value on $140 set" = **32% ratio = strike one** (bearish)
- Jabba's Sail Barge: "$280 in minifig value on $500 set" = **56% ratio = "awesome"** (bullish)
- Dark Falcon: "$100 in minifig value on $180 set" = **56% ratio = strong**
- Sorting Hat: no minifigs, $100 for electronic gimmick = bearish

**Gap:** We compute this ratio but it's just one of 30 features. They treat high minifig-to-RRP (>50%) as a strong bullish signal, especially for Star Wars. Our feature captures this, but verifying its importance ranking would be valuable.

### 2. "One-and-Done" / Remake Likelihood

A recurring signal they use that we completely lack:

- Optimus Prime: "one-and-done, LEGO will never release another transforming Optimus" = very bullish
- AT-TE: "we've had versions in 2008, 2013, 2016, 2022 — another will come" = bearish
- Mona Lisa: "Mona Lisa will never be rebuilt in LEGO again" = bullish for discount play
- Jabba's Sail Barge: "first UCS version, decades before another" = bullish
- Gringotts: "LEGO's done a couple Gringotts Banks, more will come" = moderate

**Quantifiable proxy features:**
- `prior_versions_count` — how many times has LEGO made this vehicle/subject before?
- `years_since_last_version` — longer gap = more pent-up demand
- `is_first_ucs` — binary: first UCS/large-scale version of this subject

These could be derived from BrickSet/Rebrickable data by matching set names or subjects.

### 3. Shelf Life as Demand Signal (Nuanced View)

Episode 40 treated short shelf life as purely bullish. Episode 39 reveals a more nuanced mental model:

- **Kevin's view:** 3-4yr shelf life = "sweet spot of failure", concerning for investment
- **DG's counter:** Long shelf life = LEGO kept it because demand is high; supply concern is offset by velocity
- **Resolution:** Shelf life interacts with sales velocity. Long shelf life + high velocity = positive (AT-TE sells well). Long shelf life + low velocity = negative (set is stale).

**Feature idea:** `shelf_life_x_velocity` interaction term, not just raw shelf life. Without velocity data, raw shelf life alone may be misleading.

### 4. "Mentions and Enthusiasm" Score — Deeper Understanding

Episode 39 reveals more structure to their tracking system:

- They maintain a table with columns: **set name, total mentions, enthusiasm score, mentions against**
- Enthusiasm score is on a ~1-3 scale (2.6 = high, 1.1 = low)
- They also have a "not top sets" table tracking negative sentiment
- High mentions + low enthusiasm = crowded/bad (Sorting Hat: 19 mentions, 1.1 enthusiasm)
- Low mentions + high enthusiasm = sleeper/good (Sail Barge: 17 mentions, 1.6 but they think too low)
- Very high mentions = investor saturation risk (Fast & Furious: 83 mentions = "gives me pause")

**Key insight:** The enthusiasm score disambiguates between "popular = good demand" and "popular = too many investors." This is a **contrarian signal** — they prefer sets that are NOT popular with investors.

**Proxy we could build:** Scrape YouTube/Reddit/BrickSet forum for set mentions and sentiment. Very high effort but high signal.

### 5. "Stale" Factor — Discount History Trajectory

Not just "has it been discounted" but the trajectory matters:

- AT-TE: "on sale consistently at 20% off... starting to feel stale" = bearish momentum
- Gringotts: "sold out since mid-December" = opposite of stale
- Great Pyramid: "on sale a lot recently, back up after holidays" = seasonal discount, not permanent

**Feature idea:** `discount_trajectory` — is the discount getting deeper over time (bearish) or is the set recovering to full price (bullish)? Our existing `kp_price_trend` partially captures this but was disabled with all Keepa features.

### 6. Sold-Out-Early / Supply Constraint Signal

Gringotts is their strongest conviction pick specifically because it sold out months before scheduled retirement:

- "Sold out since mid-December... $900 on eBay, retails for $430"
- "This has already retired early whether LEGO admits it or not"

**Feature idea:** `sold_out_before_retire` — binary or continuous (months of stock-out before retirement). This is a powerful signal for sets that genuinely run out of stock.

**Data source:** Keepa stock-out dates, or lego.com availability tracking.

### 7. Retailer Exclusivity Effect

They distinguish between retail channels:

- "Walmart exclusives don't do as well as Target exclusives" (Executor SSD)
- "Target exclusive" (Invisible Hand — did better)
- "LEGO exclusive" (Gringotts — strongest)
- "Available at Costco" (Fountain Garden in Ep 40 — death nail)

**Feature idea:** `retail_channel` — ordinal or categorical: LEGO exclusive > Target exclusive > Amazon > Walmart > mass retail/Costco

**Data source:** Would need to track where each set is sold. Not currently in our DB.

### 8. UCS / "First-Ever" Premium

For high-end sets, being the first UCS version of a vehicle is extremely bullish:

- "The first of these large Star Wars ships historically do really, really well"
- First UCS Jabba's Sail Barge — strong conviction
- UCS AT-AT retired: $850 retail -> $1300+ on eBay

**Feature idea:** `is_ucs` or `is_collector_edition` combined with `is_first_version_at_scale`

### 9. Price Point Psychology — Investor Barrier

High price points scare off investors, reducing competition:

- "$500 price point... scares a lot of investors off because that is a lot of money to put into one set"
- This acts as a natural barrier to investor saturation

**Feature idea:** We have `price_tier` (ordinal 1-8) but this specific insight suggests a non-linear effect where very high price tiers (>$300) actually benefit from reduced investor competition. Could be captured as `high_price_barrier` binary.

### 10. Comparable Set Performance — Formalized

They do this systematically for every set by looking up:
1. Prior versions of the same vehicle/subject
2. Same product line (e.g., all retired Speed Champions)
3. Same sub-theme (e.g., all Starship Collection sets)

Examples from this episode:
- Speed Champions: "Ferrari 812, Pagani Utopia, Porsche 963 — none above retail yet"
- AT-TE: "2008 version, 2013 version — values came down because of this set"
- Architecture landmarks: "Taj Mahal retired end of 24, showing $124 vs $130 retail"
- UCS ships: "Razor Crest $600 -> $720, AT-AT $850 -> $1300"
- Starship Collection: "Tantive IV available 40-60% off, still below MSRP"

**Feature idea:** `product_line_avg_growth` — average post-retirement growth of previously retired sets in the same product line/sub-theme. This is more specific than our `subtheme_loo` which averages ALL sets in a subtheme rather than just the recent product line.

### 11. Electronic / Gimmick Penalty

Sorting Hat's $100 price is considered bad specifically because of the shoehorned electronic feature:

- "This just gets away from the core of what LEGO is, which is unplugged analog play"
- They see the electronic component as adding $40+ to price without adding investment value

**Feature idea:** `has_electronics` binary (sound brick, powered up, etc.). These sets are structurally overpriced relative to parts count.

### 12. Macro Timing / External Events

- "Space race is heating up" = bullish for NASA/space sets (Perseverance)
- "Fast and Furious... more movies on their way" = media pipeline matters
- "Mandalorian movie comes out in 26" = drives Razor Crest higher

We can't easily quantify this, but it's worth noting as a human-judgment layer our ML won't capture.

---

## Consolidated Feature Priority (Combining Both Episodes)

### Tier A: Easy Wins (data exists, just need to compute)

| Feature | Source | Effort | Notes |
|---------|--------|--------|-------|
| `shelf_life_months` | lego_items.release_date, retire_date | Trivial | Ep 39+40 top signal |
| `retire_quarter` | lego_items.retire_date | Trivial | July vs Dec dynamics |
| `retires_before_q4` | lego_items.retire_date | Trivial | Binary: retire_month < 10 |
| Verify `mfig_value_to_rrp` importance | Already exists | None | Confirm it's weighted enough |

### Tier B: Cherry-Pick from Existing Keepa Data

| Feature | Source | Effort | Notes |
|---------|--------|--------|-------|
| `never_discounted` | keepa_snapshots | Low | Binary: max discount < 5% over 12+ months |
| `discount_trajectory` | keepa_snapshots | Low | Is discount deepening or recovering? |
| `sold_out_months` | keepa_snapshots | Medium | Months of Amazon stock-out pre-retirement |

### Tier C: New Data Collection Needed

| Feature | Source | Effort | Notes |
|---------|--------|--------|-------|
| `prior_versions_count` | BrickSet/Rebrickable | Medium | How many times remade |
| `years_since_last_version` | BrickSet/Rebrickable | Medium | Pent-up demand proxy |
| `is_first_ucs` | Manual or BrickSet | Low-Med | First large-scale version |
| `has_electronics` | BrickSet/manual | Low | Sound brick, powered up, etc |
| `retail_channel` | New scraping | High | Where the set is sold |
| `product_line_series` | NLP on set names | Medium | Beyond theme/subtheme |

### Tier D: Very High Effort / Human Judgment

| Feature | Source | Effort | Notes |
|---------|--------|--------|-------|
| Investor saturation / mentions | YouTube/Reddit scraping | Very High | Contrarian signal |
| Media pipeline trajectory | Manual/subjective | N/A | Upcoming movies/shows |
| Macro timing (space race, etc.) | External | N/A | Non-quantifiable |

---

## Key Takeaway vs Episode 40

Episode 39 reinforces Episode 40's findings but adds important nuance:

1. **Shelf life is not simply "shorter = better"** — it interacts with sales velocity. Long shelf life + high demand (AT-TE) can still be bullish. Without velocity data, raw shelf life could be misleading.

2. **"One-and-done" is a powerful signal** we completely lack. Whether LEGO will remake a set is central to their investment thesis. Proxies exist in historical BrickSet data.

3. **Investor saturation is their biggest risk factor** — and it's the hardest for us to capture. Their "mentions table" is essentially a crowd-sourcing moat. Sets at the top of their mentions table (83 mentions for Fast & Furious) are explicitly flagged as risky.

4. **Product line performance > theme performance** — "all Starship Collection sets see 40-60% discounts then recover" is more actionable than "Star Wars sets average X% growth."

5. **The hosts disagree frequently** — shelf life, AT-TE, Piranha Plant (Ep 40). This suggests these signals have interaction effects that simple features won't fully capture. The disagreements often come down to different weightings of supply (Kevin) vs demand (DG).
