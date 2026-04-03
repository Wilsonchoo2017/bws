# 16 - Google Trends Deep Dive

## Setup

- 113 GT sets with growth data (78 with parseable time series)
- Keywords are "LEGO {set_number}" (captures hardcore collector interest)
- 223 weekly data points per set

## Findings

### GT Does NOT Predict Growth

Best correlation: r=-0.198 (gt_n_spikes). No GT feature exceeds r=0.2.
Every model ablation shows GT degrades or matches intrinsics-only.

### GT Does NOT Capture What the Model Misses

Residual analysis: GT features correlate with model residuals at max r=0.056.
The information in GT is already absorbed by theme/subtheme features.

### The Hidden Gem Pattern

| Growth Tier | GT Mean Interest | Nonzero Weeks | Interpretation |
|-------------|-----------------|---------------|----------------|
| <5% (losers) | 2.08 | 4.2% | Low interest, low growth |
| 5-10% | 2.05 | 3.7% | Low interest, low growth |
| 10-15% | **4.08** | **11.8%** | HIGH interest, moderate growth = priced in |
| 15-20% | 1.40 | 2.9% | Low interest, high growth |
| **20%+ (winners)** | **0.83** | **1.0%** | **LOWEST interest, HIGHEST growth = hidden gems** |

The biggest winners are sets nobody is googling by set number. They're undiscovered by the collector community.

### What GT Actually Measures

Searching "LEGO 75335" captures hardcore collectors who already know the set number. This population:
- Already knows about well-known sets (Millennium Falcon, Yoda) -> these are priced in
- Doesn't search for hidden gems (cheap Minecraft, small BrickHeadz) -> these appreciate most

### Possible Future Approaches

1. **GT as anti-signal**: High GT interest = "the market already knows" = lower expected alpha
2. **Search by set name**: "LEGO Axolotl House" captures broader consumer interest, not just collectors
3. **GT relative to theme**: A Minecraft set with unusually high GT vs other Minecraft sets = differentiated
4. **GT as confidence modifier**: High GT = more certain prediction, Low GT = more uncertainty

### Verdict

GT by set number is not a predictive feature for growth. It captures market awareness, which is inversely correlated with alpha. The model's existing features (theme, subtheme, pricing) already capture the useful information.

Do not add GT features to the production model. Consider GT only as a confidence/risk adjustment signal.
