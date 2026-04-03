# Research Findings: LEGO Set Investment Return Prediction

16 experiments across EDA, feature engineering, model tuning, portfolio optimization, and Google Trends analysis.

## Best Model (322 sets)

**GBM** (d=4, leaf=6, n=250, lr=0.02) with 14 intrinsic features:
- **LOO R2 = 0.479, Corr = 0.699, MAE = 3.90%, AUC = 0.861**
- Top features: subtheme_loo (38%), theme_bayes (36%), usd_gbp_ratio (12%), minifig_density (7%)

## Best Portfolio Strategy

| Horizon | Strategy | Expected Return |
|---------|----------|----------------|
| 12m, small budget | ML Optimizer (conservative) | +23.8% |
| 12m, large budget | Top Predicted Growth | +34.2% |
| 24m | Concentrated top picks | +99.0% |

Cheap sets ($10-35) dominate every optimal portfolio. Diversification across 10+ themes provides the best Sharpe ratio.

## Key Insights

1. **Theme identity is king** -- subtheme + theme explain ~75% of feature importance
2. **More data > more features** -- R2 improved from 0.27 (157 sets) to 0.48 (322 sets) with same features
3. **Keepa buy box premium at OOS** is the strongest non-intrinsic feature (r=+0.54) but only useful at retirement moment
4. **Google Trends is an anti-signal** -- biggest winners have least GT interest (hidden gems). See [16_gt_deep_dive.md](16_gt_deep_dive.md)
5. **LEGO investing has 80%+ base win rate** -- ML value is in ranking (which sets), not sizing (how much)

## Production Files

| File | Purpose |
|------|---------|
| `services/ml/growth_model.py` | Tiered growth prediction (Tier 1: intrinsics, Tier 2: +Keepa) |
| `services/ml/kelly_optimizer.py` | Per-set ML Kelly sizing |
| `services/ml/portfolio_optimizer.py` | Mean-Variance knapsack portfolio optimizer |
| `services/scoring/provider.py` | Pluggable scoring provider protocol |
| `services/scoring/growth_provider.py` | Growth model as scoring provider |

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /ml/growth/predictions` | All ML growth predictions |
| `GET /ml/growth/predictions/{set_number}` | Single set prediction |
| `GET /ml/kelly?budget=X&max_positions=N` | ML Kelly position sizing |
| `GET /ml/portfolio?budget=1000&risk=balanced` | Optimized portfolio |
| `POST /ml/growth/retrain` | Force retrain models |
| `GET /items/signals` | Enriched with ML predictions via scoring providers |

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

## Next Steps

1. **More data** -- 322 sets now, re-run at 500+
2. **Pre-retirement Keepa** -- capture Amazon discount while in stock
3. **Live tracking** -- record predictions, compare to actual 12/24m returns
4. **HP re-tune** -- sweep running on 322 sets
