# Research Findings: LEGO Set Investment Return Prediction

15 experiments across EDA, feature engineering, model tuning, and portfolio optimization.

## Summary

**Best growth model**: GBM with 14 features (Bayesian theme + subtheme LOO + intrinsics)
- LOO R2=0.337, AUC=0.810, MAE=4.54% on 214 sets
- Top features: subtheme_loo (60%), theme_bayes (46%), minifig_density (17%)

**Best portfolio strategy**: Depends on horizon and budget
- 12m, small budget: ML Optimizer (conservative) +23.8%
- 12m, large budget: Top Predicted Growth +34.2%
- 24m: Concentrated top picks +99.0%

**Key insight**: LEGO investing has an 80%+ base win rate. The ML model's value is ranking (which sets to buy), not sizing (how much). Cheap sets ($10-35) with high predicted growth dominate every optimal portfolio.

## Detailed Findings

| File | Experiments | Topic |
|------|-------------|-------|
| [01_eda_and_leakage.md](01_eda_and_leakage.md) | 01-04 | EDA, data leakage discovery, temporal model |
| [02_feature_engineering.md](02_feature_engineering.md) | 05-10 | Feature experiments, Keepa timeline, Google Trends, subtheme |
| [03_model_tuning.md](03_model_tuning.md) | 11-12 | HP tuning, preprocessing, best production model |
| [04_portfolio_optimization.md](04_portfolio_optimization.md) | 13-15 | Kelly criterion, mean-variance optimizer, backtest |

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

## Next Steps

1. **More data** -- scraper running, re-run experiments at 400+ sets
2. **Google Trends** -- cultural relevance signal for breakout sets (need 100+ retail sets)
3. **Pre-retirement Keepa** -- capture Amazon discount while still in stock
4. **Live tracking** -- record predictions, compare to actual returns in 12/24 months
