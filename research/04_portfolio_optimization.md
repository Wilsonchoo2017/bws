# Portfolio Optimization & Backtest


## 13 - ML Kelly Criterion & Portfolio Optimization

### Problem Statement

The end goal of the ML model is **profit**. But translating growth predictions into actual buying decisions requires solving a constrained optimization:

- **Each set has a different price** (MYR 40 to MYR 3,700+)
- **Budget is limited** (can't buy everything)
- **Storage/capital lockup costs** mean we need sets to beat an opportunity cost (~8% annually)
- **Drawdown risk**: some predictions will be wrong, losing capital
- **Diversification**: concentrating on few sets = higher expected return but higher variance
- **Indivisibility**: you buy whole sets, not fractions

### Current Kelly Implementation

The old system bins sets by composite signal score and uses historical bin-level win rates. Every set in the same bin gets the same Kelly fraction. This ignores per-set ML predictions entirely.

### ML Kelly: What We Built

We replaced bin-level Kelly with **per-set Kelly fractions** derived from:

1. ML model predicts expected growth for each set
2. LOO residuals define prediction error distribution (mean=+0.16%, std=5.67%)
3. Monte Carlo simulation: `actual_return ~ predicted_growth + Normal(0.16, 5.67)`
4. From simulated distribution: per-set win probability and payoff ratio
5. Kelly: `f* = (b*p - q) / b` with profit threshold at 8% (opportunity cost)
6. Half-Kelly + confidence discount + position cap

**Result**: Every set gets a unique, calibrated bet size.

### What We Learned

**LEGO sets almost always appreciate.** With prediction std=5.67% and most sets predicted at 4%+, even mediocre sets have >25% win probability against the 8% bar. The classic Kelly formula says "bet on almost everything" which is mathematically correct but practically useless.

**The ML model's real value is ranking, not sizing.** Top 10 sets: expected 27.3% return. All 223 sets: expected ~15%. The value is in selection, not allocation within the selected pool.

### The Real Optimization Problem (Unsolved)

What we actually need is a **constrained portfolio optimizer** that solves:

```
Maximize: Expected portfolio return
Subject to:
  - Total cost <= budget (e.g., MYR 5,000)
  - Each set is a whole unit (integer constraint -- can't buy 0.3 of a set)
  - Each set has a fixed price (RRP or market price)
  - Max position in any single set (e.g., 2 units)
  - Minimum diversification (e.g., at least 5 different sets)
  - Risk constraint: portfolio drawdown < X% at 95% confidence
```

This is a **knapsack problem with uncertainty**:
- Items = LEGO sets, each with a price (weight) and predicted return (value)
- But the "value" is uncertain -- it's a distribution, not a point estimate
- We want to maximize expected return while controlling for downside risk

### Proposed Model: Mean-Variance Knapsack

**Inputs:**
- For each set: price, predicted_growth (from ML), prediction_std (from calibration)
- Budget constraint
- Risk tolerance parameter

**Approach:**
1. **Return vector**: ML predicted growth for each set
2. **Covariance matrix**: Theme-level correlations (Minecraft sets move together, etc.) + prediction error
3. **Markowitz-style objective**: Maximize `expected_return - lambda * portfolio_variance`
4. **Integer programming**: Each set is 0 or 1 (or 0 to max_units), price must fit budget

This accounts for:
- **Price differences**: A MYR 40 set and MYR 2,000 set compete for the same budget
- **Correlation**: Don't put everything in Minecraft even if it's the best theme
- **Uncertainty**: High-growth predictions with low confidence get penalized
- **Diversification**: Variance penalty naturally diversifies across themes

### Implementation Roadmap

1. **Phase 1** (done): ML growth predictions + basic Kelly sizing
2. **Phase 2** (next): Estimate theme-level return correlations from data
3. **Phase 3**: Integer programming portfolio optimizer (scipy or PuLP)
4. **Phase 4**: Backtest the optimizer -- would this portfolio have beaten naive "buy top N"?

### Why This Matters

The difference between "buy the top 10 cheapest high-growth sets" and "optimally allocate MYR 5,000 across sets considering price, correlation, and risk" could be significant. A MYR 40 Minecraft set at 25% growth might be a better buy than a MYR 500 Star Wars set at 20% growth -- but only if you account for how many of each you can afford and how correlated they are with the rest of your portfolio.

### Files Created
- `services/ml/kelly_optimizer.py` -- Per-set ML Kelly sizing with calibrated error distribution
- `services/ml/growth_model.py` -- Tiered growth prediction model
- `services/scoring/provider.py` -- Pluggable scoring provider protocol
- `services/scoring/growth_provider.py` -- Growth model as a scoring provider
- API: `GET /ml/kelly?budget=500000&max_positions=10`

---

## 14 - Mean-Variance Portfolio Optimizer

### What We Built

A constrained portfolio optimizer that solves: "Given budget X, which specific LEGO sets should I buy and how many of each?"

**Model**: Mean-Variance Knapsack using scipy MILP
- **Objective**: Maximize risk-adjusted return per dollar
- **Constraints**: Budget, integer units (0-3 per set), theme diversification
- **Risk model**: Covariance matrix from theme structure (ICC=0.194) + prediction error (std=5.67%)

### Strategy Comparison ($1,000 budget)

| Strategy | Return | Std | Sharpe | VaR 95% | Sets | Themes |
|----------|--------|-----|--------|---------|------|--------|
| **MV Optimizer** | 19.6% | **3.3%** | 5.89 | 14.1% | **28** | **12** |
| Top Growth (naive) | **30.9%** | 6.1% | 5.09 | 20.9% | 5 | 4 |
| Best Value ($/growth) | 22.3% | 3.6% | **6.12** | 16.3% | 25 | 12 |
| Theme Diversified | 24.1% | 4.5% | 5.39 | 16.7% | 9 | 5 |

### Key Findings

1. **Naive "buy top growth" is a trap.** Highest return (30.9%) but highest risk -- 5 sets across 4 themes. One bad theme wipes the portfolio.

2. **MV Optimizer delivers lowest risk** (3.3% std) via maximum diversification (28 sets, 12 themes). Trades ~11% return for ~50% less volatility.

3. **Best Value (growth per dollar) is the strongest simple strategy.** Sharpe 6.12 without needing an optimizer. Buy cheap sets with high growth.

4. **Cheap sets dominate every portfolio.** $10-35 sets (Minecraft, Super Heroes mechs, SPEED CHAMPIONS, DUPLO) give the best bang per dollar. You can buy 3x of a $10 set for the same budget as 1x of a $30 set.

5. **Risk-return tradeoff across budgets:**

| Budget | Strategy | Return | Sharpe | Sets | Themes |
|--------|----------|--------|--------|------|--------|
| $500 | Conservative | 21.9% | 5.88 | 16 | 10 |
| $1,000 | Balanced | 19.6% | 5.89 | 28 | 12 |
| $2,000 | Balanced | 19.8% | 6.34 | 41 | 13 |
| $5,000 | Conservative | 22.3% | 7.78 | 58 | 18 |

Sharpe improves with budget because larger budgets enable better diversification.

### Covariance Structure

From 223 sets:
- **Between-theme variance**: 19% of total (theme identity explains 19% of return variance)
- **Within-theme variance**: 81% (set-specific factors dominate)
- **ICC (within-theme correlation)**: 0.194 (two sets in same theme correlate ~20%)
- **Cross-theme correlation**: ~5% (weak LEGO market factor)

### Practical Insight

The optimizer confirms what the growth model found: **theme selection matters most, but within-theme diversification is cheap insurance.** The optimal portfolio buys 2-3 units of many cheap high-growth sets across 10+ themes, rather than concentrating on a few expensive premium sets.

### Limitation

Uses historical `annual_growth_pct` as "predicted returns" (not the ML model predictions). Full integration would use `growth_model.py` predictions, which we'll do in the production module.

### Files
- `research/14_portfolio_optimizer.py` -- Research experiment with strategy comparison
- `services/ml/portfolio_optimizer.py` -- Production module
- API: `GET /ml/portfolio?budget=1000&risk=balanced&max_units=3`

---

## 15 - Backtest: Would the optimizer have made money?

Simulated buying sets at RRP using LOO predictions, measured actual returns from candlestick data at 12m and 24m horizons. 41 sets (mostly 2019 cohort).

### 12-Month Returns ($500 budget)

| Strategy | Return | Profit | Sets | Themes | Win% |
|----------|--------|--------|------|--------|------|
| ML Optimizer (conservative) | **+23.8%** | **$119** | 13 | 5 | 77% |
| Equal Weight | +22.3% | $111 | 24 | 7 | 79% |
| ML Optimizer (aggressive) | +16.0% | $79 | 14 | 5 | 79% |
| Best Growth/Dollar | +15.5% | $76 | 13 | 5 | 77% |
| Top Predicted Growth | +6.6% | $33 | 6 | 3 | 83% |
| ORACLE (perfect foresight) | +51.4% | $256 | 10 | 5 | 100% |

### 12-Month Returns ($1000 budget)

| Strategy | Return | Profit | Sets | Themes | Win% |
|----------|--------|--------|------|--------|------|
| Top Predicted Growth | **+34.2%** | **$342** | 11 | 5 | 82% |
| ML Optimizer (balanced) | +26.3% | $262 | 19 | 8 | 84% |
| Best Growth/Dollar | +26.3% | $262 | 19 | 8 | 84% |
| ML Optimizer (conservative) | +21.6% | $216 | 15 | 6 | 73% |
| Equal Weight | +20.5% | $196 | 33 | 9 | 82% |
| ORACLE | +37.6% | $373 | 16 | 6 | 100% |

### 24-Month Returns ($500 budget)

| Strategy | Return | Profit | Sets | Themes | Win% |
|----------|--------|--------|------|--------|------|
| Top Predicted Growth | **+99.0%** | **$494** | 6 | 3 | 100% |
| ML Optimizer (conservative) | +71.6% | $357 | 13 | 5 | 92% |
| ML Optimizer (aggressive) | +67.1% | $331 | 14 | 5 | 93% |
| Best Growth/Dollar | +57.4% | $283 | 13 | 5 | 92% |
| Equal Weight | +55.5% | $276 | 24 | 7 | 92% |
| ORACLE | +78.4% | $387 | 13 | 6 | 100% |

### Key Findings

1. **All strategies made money.** Even the weakest (top predicted growth at $500/12m: +6.6%) was profitable. LEGO investing has a very high base rate of success.

2. **At 12 months, the ML optimizer (conservative) beats equal weight** ($500: 23.8% vs 22.3%). The optimizer concentrates on higher-growth sets while maintaining 5 themes of diversification.

3. **At larger budgets ($1000), top predicted growth wins** (+34.2%). With more budget, you can afford to concentrate on high-conviction picks. The optimizer over-diversifies at this budget level.

4. **At 24 months, concentrated strategies dominate.** Top predicted growth returns +99% ($500 doubles). Time heals diversification -- if you hold long enough, most sets appreciate and the best picks compound.

5. **The optimizer's value is risk management, not return maximization.** It consistently delivers 77-93% win rates with controlled theme concentration. The naive strategy sometimes wins higher returns but is more exposed to theme-specific risk.

6. **LOO prediction correlation is only 0.12** on these 41 candlestick sets (mostly 2019 Star Wars). The model was trained on the full 223-set dataset where correlation is 0.58. This subset is harder because it's dominated by one theme.

### Honest Assessment

The optimizer beat equal-weight at small budgets and short horizons, but underperformed concentrated strategies at larger budgets and longer horizons. This is the classic diversification tradeoff:
- **Small budget / short horizon**: diversification protects against bad picks → optimizer wins
- **Large budget / long horizon**: most LEGO sets appreciate eventually → concentration wins

**Recommendation**: Use the optimizer for short-term (12m) decisions and smaller allocations. For long-term holds (24m+), lean toward concentrated positions in the model's top picks.

### Limitation

Only 41 sets with actual price history, dominated by 2019 Star Wars. Need more historical data across themes and years for a robust backtest.
