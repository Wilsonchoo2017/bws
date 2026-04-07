"""Walk-forward backtest with algotrading metrics.

Simulates buying LEGO sets based on model predictions using temporal
walk-forward: train on years 1..N, "trade" year N+1. Evaluates with
metrics borrowed from quantitative trading.

MYR_PER_USD = 4.50 (Malaysian Ringgit).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.preprocessing import PowerTransformer, StandardScaler

from services.ml.growth.model_selection import _get_monotonic_constraints, build_model

logger = logging.getLogger(__name__)

MYR_PER_USD = 4.50
HURDLE_RATE = 8.0  # minimum acceptable return %


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    """One simulated buy-and-hold trade."""

    set_number: str
    theme: str
    buy_year: int  # year we "buy" (retirement year)
    predicted_growth: float
    actual_growth: float
    avoid_probability: float
    rrp_usd_cents: int
    cost_myr: float
    profit_myr: float
    return_pct: float
    is_winner: bool  # actual > hurdle


@dataclass
class BacktestResult:
    """Full backtest report card."""

    # Strategy
    strategy_name: str
    top_pct: float  # what % of sets we bought each year
    hurdle_rate: float
    n_years: int

    # Trades
    trades: list[Trade]
    n_trades: int
    n_winners: int
    n_losers: int

    # P&L
    total_invested_myr: float
    total_profit_myr: float
    total_return_pct: float

    # Core trading metrics
    win_rate: float  # % of trades above hurdle
    avg_winner_pct: float  # mean return of winners
    avg_loser_pct: float  # mean return of losers
    profit_factor: float  # gross profit / gross loss
    expected_value_per_trade_myr: float
    risk_reward_ratio: float  # avg winner / avg loser (absolute)

    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float  # annual return / max drawdown
    worst_trade_pct: float
    best_trade_pct: float

    # Yearly breakdown
    yearly_returns: dict[int, float]  # year -> return %
    yearly_win_rates: dict[int, float]

    # Quintile analysis
    quintile_returns: dict[int, float]  # quintile 1-5 -> avg actual return
    quintile_hit_rates: dict[int, float]  # quintile 1-5 -> % above hurdle

    # Classifier value-add
    clf_safe_return: float | None  # avg return when clf says safe
    clf_avoid_return: float | None  # avg return when clf says avoid
    clf_veto_count: int  # trades clf would have prevented
    clf_veto_avg_return: float | None  # avg return of vetoed trades

    def format_report(self) -> str:
        """Human-readable report card."""
        lines = [
            f"\n{'=' * 65}",
            f"  BACKTEST REPORT: {self.strategy_name}",
            f"  {self.n_years} years, top {self.top_pct:.0f}% picks, {self.hurdle_rate:.0f}% hurdle",
            f"{'=' * 65}",
            "",
            "  P&L SUMMARY",
            f"    Total invested:     RM {self.total_invested_myr:,.0f}",
            f"    Total profit:       RM {self.total_profit_myr:,.0f}",
            f"    Total return:       {self.total_return_pct:+.1f}%",
            "",
            "  TRADE STATISTICS",
            f"    Trades:             {self.n_trades}",
            f"    Win rate:           {self.win_rate:.0f}% ({self.n_winners}W / {self.n_losers}L)",
            f"    Avg winner:         +{self.avg_winner_pct:.1f}%",
            f"    Avg loser:          +{self.avg_loser_pct:.1f}%",
            f"    Profit factor:      {self.profit_factor:.2f}x",
            f"    Risk/reward:        {self.risk_reward_ratio:.2f}x",
            f"    EV per trade:       RM {self.expected_value_per_trade_myr:.0f}",
            "",
            "  RISK METRICS",
            f"    Sharpe ratio:       {self.sharpe_ratio:.2f}",
            f"    Sortino ratio:      {self.sortino_ratio:.2f}",
            f"    Max drawdown:       {self.max_drawdown_pct:.1f}%",
            f"    Calmar ratio:       {self.calmar_ratio:.2f}",
            f"    Best trade:         +{self.best_trade_pct:.1f}%",
            f"    Worst trade:        +{self.worst_trade_pct:.1f}%",
            "",
            "  YEARLY RETURNS",
        ]
        for yr in sorted(self.yearly_returns):
            wr = self.yearly_win_rates.get(yr, 0)
            lines.append(f"    {yr}: {self.yearly_returns[yr]:+.1f}% (win rate {wr:.0f}%)")

        lines.extend([
            "",
            "  MODEL RANKING (quintile analysis)",
        ])
        for q in sorted(self.quintile_returns):
            label = {1: "Top 20%", 2: "20-40%", 3: "40-60%", 4: "60-80%", 5: "Bot 20%"}
            hr = self.quintile_hit_rates.get(q, 0)
            lines.append(
                f"    Q{q} ({label.get(q, '')}): {self.quintile_returns[q]:+.1f}% "
                f"(hit rate {hr:.0f}%)"
            )

        if self.clf_safe_return is not None:
            lines.extend([
                "",
                "  CLASSIFIER VALUE",
                f"    Safe picks avg:     +{self.clf_safe_return:.1f}%",
                f"    Avoid picks avg:    +{self.clf_avoid_return:.1f}%"
                if self.clf_avoid_return is not None else "",
                f"    Would have vetoed:  {self.clf_veto_count} trades",
                f"    Vetoed avg return:  +{self.clf_veto_avg_return:.1f}%"
                if self.clf_veto_avg_return is not None else "",
            ])

        lines.append(f"{'=' * 65}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------


def run_backtest(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    feature_names: list[str],
    *,
    df_meta: pd.DataFrame | None = None,
    top_pct: float = 20.0,
    hurdle_rate: float = HURDLE_RATE,
    min_train_years: int = 3,
    target_transform: str = "yeo-johnson",
) -> BacktestResult:
    """Walk-forward backtest: train on years 1..N, trade year N+1.

    Args:
        X: Feature matrix (n_samples, n_features), already filled.
        y: Target (annual_growth_pct).
        groups: Retirement year per sample.
        feature_names: For monotonic constraints.
        df_meta: Optional DataFrame with set_number, theme, rrp_usd_cents.
        top_pct: Buy the top X% of model's ranked predictions each year.
        hurdle_rate: Minimum acceptable return %.
        min_train_years: Need at least this many years before trading.
        target_transform: "yeo-johnson" or "none".
    """
    from services.ml.growth.classifier import _build_classifier, make_avoid_labels

    groups = np.asarray(groups, dtype=float)
    finite = np.isfinite(groups)
    unique_years = sorted(set(groups[finite].astype(int)))

    if len(unique_years) < min_train_years + 1:
        raise ValueError(
            f"Need {min_train_years + 1} year groups, got {len(unique_years)}"
        )

    groups_int = np.full(len(groups), -9999, dtype=int)
    groups_int[finite] = groups[finite].astype(int)

    mono = _get_monotonic_constraints(feature_names)
    all_trades: list[Trade] = []

    for i in range(min_train_years, len(unique_years)):
        test_year = unique_years[i]
        train_years = set(unique_years[:i])

        train_mask = np.isin(groups_int, list(train_years))
        test_mask = groups_int == test_year

        if test_mask.sum() < 3:
            continue

        X_tr, X_te = X[train_mask], X[test_mask]
        y_tr, y_te = y[train_mask], y[test_mask]

        # Train regressor
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        pt = None
        y_tr_fit = y_tr
        if target_transform == "yeo-johnson":
            pt = PowerTransformer(method="yeo-johnson", standardize=False)
            y_tr_fit = pt.fit_transform(y_tr.reshape(-1, 1)).ravel()

        reg = build_model({"max_depth": 5, "num_leaves": 20, "min_child_samples": 10})
        if mono:
            reg.set_params(monotone_constraints=mono)
        reg.fit(X_tr_s, y_tr_fit)
        y_pred = reg.predict(X_te_s)
        if pt is not None:
            y_pred = pt.inverse_transform(y_pred.reshape(-1, 1)).ravel()

        # Train classifier
        y_bin_tr = make_avoid_labels(y_tr, hurdle_rate)
        clf = _build_classifier()
        clf.fit(X_tr_s, y_bin_tr)
        avoid_prob = clf.predict_proba(X_te_s)[:, 1]

        # Select top_pct% by predicted growth
        n_buy = max(1, int(len(y_te) * top_pct / 100))
        buy_idx = np.argsort(y_pred)[::-1][:n_buy]

        # Build trades
        test_indices = np.where(test_mask)[0]
        for local_i in buy_idx:
            global_i = test_indices[local_i]
            actual = float(y_te[local_i])
            pred = float(y_pred[local_i])
            ap = float(avoid_prob[local_i])

            # Get metadata if available
            sn, theme, rrp_cents = "", "", 0
            if df_meta is not None and global_i < len(df_meta):
                row = df_meta.iloc[global_i]
                sn = str(row.get("set_number", ""))
                theme = str(row.get("theme", ""))
                rrp_cents = int(pd.to_numeric(row.get("rrp_usd_cents", 0), errors="coerce") or 0)

            cost_myr = rrp_cents / 100 * MYR_PER_USD if rrp_cents > 0 else 100 * MYR_PER_USD
            profit_myr = cost_myr * actual / 100

            all_trades.append(Trade(
                set_number=sn,
                theme=theme,
                buy_year=test_year,
                predicted_growth=pred,
                actual_growth=actual,
                avoid_probability=ap,
                rrp_usd_cents=rrp_cents,
                cost_myr=round(cost_myr, 2),
                profit_myr=round(profit_myr, 2),
                return_pct=round(actual, 1),
                is_winner=actual >= hurdle_rate,
            ))

    return _compute_metrics(all_trades, top_pct, hurdle_rate, unique_years, min_train_years)


def _compute_metrics(
    trades: list[Trade],
    top_pct: float,
    hurdle_rate: float,
    unique_years: list[int],
    min_train_years: int,
) -> BacktestResult:
    """Compute all algotrading metrics from trade list."""
    if not trades:
        return _empty_result(top_pct, hurdle_rate)

    returns = np.array([t.return_pct for t in trades])
    profits = np.array([t.profit_myr for t in trades])
    costs = np.array([t.cost_myr for t in trades])

    n = len(trades)
    winners = [t for t in trades if t.is_winner]
    losers = [t for t in trades if not t.is_winner]

    win_returns = np.array([t.return_pct for t in winners]) if winners else np.array([0.0])
    lose_returns = np.array([t.return_pct for t in losers]) if losers else np.array([0.0])

    # Core P&L
    total_invested = float(costs.sum())
    total_profit = float(profits.sum())
    total_return = total_profit / total_invested * 100 if total_invested > 0 else 0

    # Win rate and averages
    win_rate = len(winners) / n * 100
    avg_winner = float(win_returns.mean())
    avg_loser = float(lose_returns.mean())

    # Profit factor: gross profit / gross loss
    gross_profit = float(profits[profits > 0].sum()) if (profits > 0).any() else 0
    gross_loss = float(np.abs(profits[profits < 0]).sum()) if (profits < 0).any() else 0.01
    # For LEGO most are positive, so use hurdle-relative:
    # excess profit from winners vs shortfall from losers
    excess_profit = float(np.sum(returns[returns >= hurdle_rate] - hurdle_rate))
    shortfall = float(np.sum(hurdle_rate - returns[returns < hurdle_rate]))
    profit_factor = excess_profit / shortfall if shortfall > 0 else float("inf")

    # Risk-reward ratio
    avg_win_excess = avg_winner - hurdle_rate if avg_winner > hurdle_rate else 0.01
    avg_lose_shortfall = hurdle_rate - avg_loser if avg_loser < hurdle_rate else 0.01
    risk_reward = avg_win_excess / avg_lose_shortfall if avg_lose_shortfall > 0 else float("inf")

    # EV per trade
    ev = float(profits.mean())

    # Sharpe (annualized, using per-trade returns)
    rf = 3.5  # risk-free rate (Malaysia ~3.5%)
    excess = returns - rf
    sharpe = float(excess.mean() / excess.std()) if excess.std() > 0 else 0

    # Sortino (only penalize downside volatility)
    downside = returns[returns < hurdle_rate] - hurdle_rate
    downside_std = float(np.sqrt(np.mean(downside**2))) if len(downside) > 0 else 0.01
    sortino = float((returns.mean() - rf) / downside_std)

    # Max drawdown on cumulative P&L curve
    cumulative = np.cumsum(profits)
    peak = np.maximum.accumulate(cumulative)
    drawdown = (peak - cumulative)
    max_dd_myr = float(drawdown.max()) if len(drawdown) > 0 else 0
    max_dd_pct = max_dd_myr / total_invested * 100 if total_invested > 0 else 0

    # Calmar
    n_years = len(unique_years) - min_train_years
    annual_return = total_return / max(n_years, 1)
    calmar = annual_return / max_dd_pct if max_dd_pct > 0 else float("inf")

    # Yearly breakdown
    yearly_returns: dict[int, float] = {}
    yearly_win_rates: dict[int, float] = {}
    for yr in sorted(set(t.buy_year for t in trades)):
        yr_trades = [t for t in trades if t.buy_year == yr]
        yr_costs = sum(t.cost_myr for t in yr_trades)
        yr_profits = sum(t.profit_myr for t in yr_trades)
        yearly_returns[yr] = yr_profits / yr_costs * 100 if yr_costs > 0 else 0
        yearly_win_rates[yr] = sum(1 for t in yr_trades if t.is_winner) / len(yr_trades) * 100

    # Quintile analysis (by model predicted rank)
    sorted_by_pred = sorted(trades, key=lambda t: t.predicted_growth, reverse=True)
    q_size = max(1, len(sorted_by_pred) // 5)
    quintile_returns: dict[int, float] = {}
    quintile_hit_rates: dict[int, float] = {}
    for q in range(1, 6):
        start = (q - 1) * q_size
        end = q * q_size if q < 5 else len(sorted_by_pred)
        q_trades = sorted_by_pred[start:end]
        if q_trades:
            quintile_returns[q] = float(np.mean([t.actual_growth for t in q_trades]))
            quintile_hit_rates[q] = sum(1 for t in q_trades if t.is_winner) / len(q_trades) * 100

    # Classifier value analysis
    safe_trades = [t for t in trades if t.avoid_probability < 0.5]
    avoid_trades = [t for t in trades if t.avoid_probability >= 0.5]

    clf_safe_ret = float(np.mean([t.return_pct for t in safe_trades])) if safe_trades else None
    clf_avoid_ret = float(np.mean([t.return_pct for t in avoid_trades])) if avoid_trades else None

    return BacktestResult(
        strategy_name="ML Walk-Forward",
        top_pct=top_pct,
        hurdle_rate=hurdle_rate,
        n_years=n_years,
        trades=trades,
        n_trades=n,
        n_winners=len(winners),
        n_losers=len(losers),
        total_invested_myr=round(total_invested, 2),
        total_profit_myr=round(total_profit, 2),
        total_return_pct=round(total_return, 1),
        win_rate=round(win_rate, 1),
        avg_winner_pct=round(avg_winner, 1),
        avg_loser_pct=round(avg_loser, 1),
        profit_factor=round(profit_factor, 2),
        expected_value_per_trade_myr=round(ev, 2),
        risk_reward_ratio=round(risk_reward, 2),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        max_drawdown_pct=round(max_dd_pct, 1),
        calmar_ratio=round(calmar, 2),
        worst_trade_pct=round(float(returns.min()), 1),
        best_trade_pct=round(float(returns.max()), 1),
        yearly_returns=yearly_returns,
        yearly_win_rates=yearly_win_rates,
        quintile_returns=quintile_returns,
        quintile_hit_rates=quintile_hit_rates,
        clf_safe_return=round(clf_safe_ret, 1) if clf_safe_ret is not None else None,
        clf_avoid_return=round(clf_avoid_ret, 1) if clf_avoid_ret is not None else None,
        clf_veto_count=len(avoid_trades),
        clf_veto_avg_return=round(clf_avoid_ret, 1) if clf_avoid_ret is not None else None,
    )


def _empty_result(top_pct: float, hurdle_rate: float) -> BacktestResult:
    return BacktestResult(
        strategy_name="ML Walk-Forward",
        top_pct=top_pct, hurdle_rate=hurdle_rate, n_years=0,
        trades=[], n_trades=0, n_winners=0, n_losers=0,
        total_invested_myr=0, total_profit_myr=0, total_return_pct=0,
        win_rate=0, avg_winner_pct=0, avg_loser_pct=0,
        profit_factor=0, expected_value_per_trade_myr=0, risk_reward_ratio=0,
        sharpe_ratio=0, sortino_ratio=0, max_drawdown_pct=0, calmar_ratio=0,
        worst_trade_pct=0, best_trade_pct=0,
        yearly_returns={}, yearly_win_rates={},
        quintile_returns={}, quintile_hit_rates={},
        clf_safe_return=None, clf_avoid_return=None,
        clf_veto_count=0, clf_veto_avg_return=None,
    )


def run_benchmark_backtest(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    *,
    hurdle_rate: float = HURDLE_RATE,
    min_train_years: int = 3,
) -> BacktestResult:
    """Random buy benchmark: buy all sets each year (no model)."""
    groups = np.asarray(groups, dtype=float)
    finite = np.isfinite(groups)
    unique_years = sorted(set(groups[finite].astype(int)))
    groups_int = np.full(len(groups), -9999, dtype=int)
    groups_int[finite] = groups[finite].astype(int)

    trades: list[Trade] = []
    for i in range(min_train_years, len(unique_years)):
        yr = unique_years[i]
        mask = groups_int == yr
        for j in np.where(mask)[0]:
            actual = float(y[j])
            cost = 100 * MYR_PER_USD  # assume avg $100 set
            trades.append(Trade(
                set_number="", theme="", buy_year=yr,
                predicted_growth=0, actual_growth=actual,
                avoid_probability=0.5, rrp_usd_cents=10000,
                cost_myr=cost, profit_myr=round(cost * actual / 100, 2),
                return_pct=round(actual, 1),
                is_winner=actual >= hurdle_rate,
            ))

    result = _compute_metrics(trades, 100.0, hurdle_rate, unique_years, min_train_years)
    result.strategy_name = "Benchmark (buy everything)"
    return result
