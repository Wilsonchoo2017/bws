"""Signal significance audit.

Computes statistical significance (Spearman correlation + p-value),
feature importance, data coverage, and quintile monotonicity for each
signal. Produces a KEEP / WEAK / DROP verdict per signal to guide
signal pruning decisions.
"""

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd
from scipy import stats

from services.backtesting.types import MODIFIER_NAMES, SIGNAL_NAMES


class Verdict(Enum):
    """Signal audit verdict."""

    KEEP = "KEEP"
    WEAK = "WEAK"
    DROP = "DROP"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class SignalReport:
    """Statistical report for one signal."""

    signal: str
    coverage_pct: float  # % of samples with non-null values
    spearman_corr: float | None
    p_value: float | None
    is_significant: bool  # p < 0.05
    importance: float | None  # permutation importance
    quintile_spread: float | None  # Q5 median return - Q1 median return
    quintile_monotonic: bool  # returns increase across quintiles
    verdict: Verdict
    reason: str


@dataclass(frozen=True)
class AuditResults:
    """Complete signal audit output."""

    reports: list[SignalReport]
    return_column: str
    n_samples: int
    keep_signals: list[str]
    weak_signals: list[str]
    drop_signals: list[str]
    no_data_signals: list[str]


def audit_signals(
    df: pd.DataFrame,
    return_column: str,
    min_coverage_pct: float = 20.0,
    significance_level: float = 0.05,
) -> AuditResults:
    """Run a comprehensive signal audit against a return column.

    For each of the 14 signals, computes:
    1. Data coverage (% non-null)
    2. Spearman rank correlation + p-value
    3. Feature importance (via HistGradientBoostingRegressor)
    4. Quintile monotonicity and spread

    Then assigns a verdict:
    - KEEP: statistically significant AND meaningful importance
    - WEAK: some signal but not statistically reliable
    - DROP: no meaningful relationship with returns
    - NO_DATA: insufficient data to evaluate

    Args:
        df: DataFrame with signal columns and return_column.
        return_column: Column name for actual returns (e.g. return_flip_1m).
        min_coverage_pct: Minimum % coverage to evaluate a signal.
        significance_level: P-value threshold for statistical significance.
    """
    valid = df.dropna(subset=[return_column])
    n_samples = len(valid)

    if n_samples < 10:
        return AuditResults(
            reports=[],
            return_column=return_column,
            n_samples=n_samples,
            keep_signals=[],
            weak_signals=[],
            drop_signals=[],
            no_data_signals=list(SIGNAL_NAMES),
        )

    # Compute feature importances once (all signals together)
    importances = _compute_importances(valid, return_column)

    reports: list[SignalReport] = []
    for signal in SIGNAL_NAMES:
        report = _audit_one_signal(
            valid, signal, return_column, importances,
            min_coverage_pct, significance_level,
        )
        reports.append(report)

    # Sort by importance (highest first), NO_DATA last
    reports.sort(key=lambda r: (
        r.verdict != Verdict.NO_DATA,
        r.importance or 0,
    ), reverse=True)

    keep = [r.signal for r in reports if r.verdict == Verdict.KEEP]
    weak = [r.signal for r in reports if r.verdict == Verdict.WEAK]
    drop = [r.signal for r in reports if r.verdict == Verdict.DROP]
    no_data = [r.signal for r in reports if r.verdict == Verdict.NO_DATA]

    return AuditResults(
        reports=reports,
        return_column=return_column,
        n_samples=n_samples,
        keep_signals=keep,
        weak_signals=weak,
        drop_signals=drop,
        no_data_signals=no_data,
    )


def print_audit_report(results: AuditResults) -> None:
    """Print a formatted signal audit report."""
    print(f"\n  Signal Audit: {results.return_column} "
          f"(n={results.n_samples} samples)")
    print(f"  {'=' * 88}")
    print(f"  {'Signal':25s}  {'Cov%':>5s}  {'Corr':>6s}  {'p-val':>7s}  "
          f"{'Import':>7s}  {'Q-Spread':>8s}  {'Mono':>4s}  {'Verdict':>7s}")
    print(f"  {'-' * 25}  {'-' * 5}  {'-' * 6}  {'-' * 7}  "
          f"{'-' * 7}  {'-' * 8}  {'-' * 4}  {'-' * 7}")

    for r in results.reports:
        cov = f"{r.coverage_pct:5.0f}"
        corr = f"{r.spearman_corr:+.3f}" if r.spearman_corr is not None else "  N/A"
        pval = f"{r.p_value:.4f}" if r.p_value is not None else "    N/A"
        imp = f"{r.importance:.4f}" if r.importance is not None else "    N/A"
        qs = f"{r.quintile_spread:+.1%}" if r.quintile_spread is not None else "     N/A"
        mono = " Y" if r.quintile_monotonic else " N"
        if r.verdict == Verdict.NO_DATA:
            mono = "  -"

        verdict_str = r.verdict.value
        marker = ""
        if r.verdict == Verdict.KEEP:
            marker = " ***"
        elif r.verdict == Verdict.DROP:
            marker = " x"

        print(f"  {r.signal:25s}  {cov}  {corr}  {pval}  "
              f"{imp}  {qs:>8s}  {mono}  {verdict_str}{marker}")

    # Summary
    print(f"\n  Summary:")
    print(f"    KEEP ({len(results.keep_signals)}): "
          f"{', '.join(results.keep_signals) or 'none'}")
    print(f"    WEAK ({len(results.weak_signals)}): "
          f"{', '.join(results.weak_signals) or 'none'}")
    print(f"    DROP ({len(results.drop_signals)}): "
          f"{', '.join(results.drop_signals) or 'none'}")
    print(f"    NO_DATA ({len(results.no_data_signals)}): "
          f"{', '.join(results.no_data_signals) or 'none'}")

    if results.keep_signals:
        print(f"\n  Recommended signal set ({len(results.keep_signals)} signals):")
        print(f"    {results.keep_signals}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _audit_one_signal(
    df: pd.DataFrame,
    signal: str,
    return_column: str,
    importances: dict[str, float],
    min_coverage_pct: float,
    significance_level: float,
) -> SignalReport:
    """Audit a single signal."""
    n_total = len(df)

    if signal not in df.columns:
        return SignalReport(
            signal=signal, coverage_pct=0.0,
            spearman_corr=None, p_value=None, is_significant=False,
            importance=None, quintile_spread=None, quintile_monotonic=False,
            verdict=Verdict.NO_DATA, reason="Column not present",
        )

    non_null = df[signal].notna().sum()
    coverage_pct = (non_null / n_total * 100) if n_total > 0 else 0.0

    if coverage_pct < min_coverage_pct:
        return SignalReport(
            signal=signal, coverage_pct=coverage_pct,
            spearman_corr=None, p_value=None, is_significant=False,
            importance=importances.get(signal),
            quintile_spread=None, quintile_monotonic=False,
            verdict=Verdict.NO_DATA,
            reason=f"Coverage {coverage_pct:.0f}% < {min_coverage_pct:.0f}% minimum",
        )

    # Spearman correlation + p-value
    pair = df[[signal, return_column]].dropna()
    if len(pair) < 10:
        return SignalReport(
            signal=signal, coverage_pct=coverage_pct,
            spearman_corr=None, p_value=None, is_significant=False,
            importance=importances.get(signal),
            quintile_spread=None, quintile_monotonic=False,
            verdict=Verdict.NO_DATA,
            reason=f"Only {len(pair)} paired samples (need 10+)",
        )

    corr, p_value = stats.spearmanr(pair[signal], pair[return_column])
    is_significant = p_value < significance_level

    # Quintile analysis
    q_spread, q_monotonic = _quintile_analysis(pair, signal, return_column)

    # Feature importance
    importance = importances.get(signal, 0.0)

    # Verdict logic
    verdict, reason = _determine_verdict(
        coverage_pct, corr, p_value, is_significant,
        importance, q_spread, q_monotonic,
    )

    return SignalReport(
        signal=signal,
        coverage_pct=coverage_pct,
        spearman_corr=float(corr),
        p_value=float(p_value),
        is_significant=is_significant,
        importance=importance,
        quintile_spread=q_spread,
        quintile_monotonic=q_monotonic,
        verdict=verdict,
        reason=reason,
    )


def _determine_verdict(
    coverage_pct: float,
    corr: float,
    p_value: float,
    is_significant: bool,
    importance: float,
    q_spread: float | None,
    q_monotonic: bool,
) -> tuple[Verdict, str]:
    """Determine KEEP/WEAK/DROP based on multiple criteria."""
    abs_corr = abs(corr)

    # KEEP: significant correlation AND meaningful importance
    if is_significant and abs_corr >= 0.1 and importance >= 0.02:
        strength = "strong" if abs_corr >= 0.3 else "moderate"
        return Verdict.KEEP, f"Significant {strength} correlation (r={corr:+.3f}, p={p_value:.4f})"

    # KEEP: very high importance even without strong correlation
    # (captures non-linear relationships the tree model finds)
    if importance >= 0.05 and coverage_pct >= 50:
        return Verdict.KEEP, f"High feature importance ({importance:.3f})"

    # WEAK: some signal but not statistically reliable
    if is_significant and abs_corr >= 0.05:
        return Verdict.WEAK, f"Marginally significant (r={corr:+.3f}, p={p_value:.4f})"

    if importance >= 0.01 and coverage_pct >= 50:
        return Verdict.WEAK, f"Low importance ({importance:.3f}) but decent coverage"

    if q_monotonic and q_spread is not None and abs(q_spread) >= 0.02:
        return Verdict.WEAK, f"Monotonic quintiles (spread={q_spread:+.1%}) but weak stats"

    # DROP: no meaningful signal
    if abs_corr < 0.05 and importance < 0.01:
        return Verdict.DROP, f"No correlation (r={corr:+.3f}) and negligible importance"

    if not is_significant and importance < 0.02:
        return Verdict.DROP, f"Not significant (p={p_value:.4f}) and low importance"

    return Verdict.WEAK, "Borderline — review manually"


def _quintile_analysis(
    pair: pd.DataFrame,
    signal: str,
    return_column: str,
) -> tuple[float | None, bool]:
    """Compute quintile spread and monotonicity."""
    if len(pair) < 10:
        return None, False

    try:
        pair = pair.copy()
        pair["q"] = pd.qcut(pair[signal], q=5, labels=False, duplicates="drop")
    except ValueError:
        try:
            pair["q"] = pd.qcut(pair[signal], q=3, labels=False, duplicates="drop")
        except ValueError:
            return None, False

    medians = pair.groupby("q")[return_column].median()
    if len(medians) < 2:
        return None, False

    spread = float(medians.iloc[-1] - medians.iloc[0])

    # Check monotonicity: each quintile >= previous
    diffs = medians.diff().dropna()
    monotonic = bool((diffs >= -0.005).all())  # small tolerance

    return spread, monotonic


def _compute_importances(
    df: pd.DataFrame,
    return_column: str,
) -> dict[str, float]:
    """Compute permutation importance for all signals together."""
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.inspection import permutation_importance
    except ImportError:
        return {}

    signal_cols = [s for s in SIGNAL_NAMES if s in df.columns]
    valid = df[signal_cols + [return_column]].dropna(subset=[return_column])

    if len(valid) < 20:
        return {}

    x = valid[signal_cols].fillna(-1).values
    y = valid[return_column].values

    if len(set(y)) < 2:
        return {}

    model = HistGradientBoostingRegressor(
        max_iter=100, max_depth=4, random_state=42,
    )
    model.fit(x, y)

    perm = permutation_importance(model, x, y, n_repeats=10, random_state=42)
    return dict(zip(signal_cols, perm.importances_mean))
