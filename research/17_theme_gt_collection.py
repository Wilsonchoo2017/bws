"""
17 - Theme-Level YouTube Google Trends Collection
==================================================
Experiment 16 showed GT by SET NUMBER is an anti-signal (collector awareness
= priced in). This experiment tests a different hypothesis: GT by THEME NAME
on YouTube captures kid/consumer interest, which may predict theme-level
post-retirement performance.

Searches both "LEGO {theme}" and "{theme}" in a single trendspy call so
values are on the same 0-100 scale. Computes lego_share = LEGO-specific
fraction of total YouTube interest.

Run with: python research/17_theme_gt_collection.py
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.ml import LICENSED_THEMES

RESULTS_DIR = PROJECT_ROOT / "research" / "results" / "gt_themes"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path.home() / ".bws" / "bws.duckdb"

REQUEST_DELAY_SECONDS = 60
RATE_LIMIT_COOLDOWN_SECONDS = 3600
MAX_RETRIES = 2

# Themes where the bare name is a real, searchable term on YouTube.
# Licensed IPs + LEGO-original IPs with strong brand identity.
NAMED_IP_THEMES: frozenset[str] = LICENSED_THEMES | frozenset({
    "Ninjago",
    "Friends",
    "Duplo",
    "Bionicle",
    "Nexo Knights",
    "Chima",
    "Elves",
    "Monkie Kid",
    "Hidden Side",
    "Dreamzzz",
})

# Generic themes where the bare name is meaningless for GT search.
# "City", "Creator", "Classic" etc. -- we only query "LEGO {theme}" for these.


def classify_theme(theme: str) -> str:
    """Return 'named_ip' or 'generic' based on theme name."""
    return "named_ip" if theme in NAMED_IP_THEMES else "generic"


def fetch_theme_gt(
    theme: str,
    theme_type: str,
    timeframe: str,
) -> dict | None:
    """Fetch YouTube GT data for a theme. Returns summary dict or None on failure."""
    from trendspy import Trends

    keyword_lego = f"LEGO {theme}"

    if theme_type == "named_ip":
        keywords = [keyword_lego, theme]
    else:
        keywords = [keyword_lego]

    print(f"  Querying: {keywords}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            tr = Trends(request_delay=float(REQUEST_DELAY_SECONDS))
            df = tr.interest_over_time(
                keywords=keywords,
                gprop="youtube",
                geo="",
                timeframe=timeframe,
            )

            if df.empty:
                print(f"  No data returned for {theme}")
                return {
                    "theme": theme,
                    "theme_type": theme_type,
                    "keyword_lego": keyword_lego,
                    "keyword_bare": theme if theme_type == "named_ip" else "",
                    "avg_lego": 0.0,
                    "avg_bare": 0.0,
                    "peak_lego": 0,
                    "peak_bare": 0,
                    "lego_share": None,
                    "n_weeks": 0,
                }

            avg_lego = round(float(df[keyword_lego].mean()), 2)
            peak_lego = int(df[keyword_lego].max())
            n_weeks = len(df)

            if theme_type == "named_ip" and theme in df.columns:
                avg_bare = round(float(df[theme].mean()), 2)
                peak_bare = int(df[theme].max())
                total = avg_lego + avg_bare
                lego_share = round(avg_lego / total, 4) if total > 0 else None
            else:
                avg_bare = 0.0
                peak_bare = 0
                lego_share = None

            print(
                f"  {theme}: avg_lego={avg_lego}, avg_bare={avg_bare}, "
                f"lego_share={lego_share}, n_weeks={n_weeks}"
            )

            return {
                "theme": theme,
                "theme_type": theme_type,
                "keyword_lego": keyword_lego,
                "keyword_bare": theme if theme_type == "named_ip" else "",
                "avg_lego": avg_lego,
                "avg_bare": avg_bare,
                "peak_lego": peak_lego,
                "peak_bare": peak_bare,
                "lego_share": lego_share,
                "n_weeks": n_weeks,
            }

        except Exception as exc:
            error_str = str(exc)
            is_rate_limit = "429" in error_str or "Too Many" in error_str

            if is_rate_limit:
                print(
                    f"  Rate limited on {theme}. "
                    f"Cooling down {RATE_LIMIT_COOLDOWN_SECONDS}s..."
                )
                time.sleep(RATE_LIMIT_COOLDOWN_SECONDS)
                continue

            print(f"  Attempt {attempt}/{MAX_RETRIES} failed for {theme}: {error_str}")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_DELAY_SECONDS)
                continue

            print(f"  FAILED: {theme} after {attempt} attempts")
            return None

    return None


def main() -> None:
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    timeframe = f"2018-01-01 {today}"

    print("=" * 70)
    print("EXPERIMENT 17: Theme-Level YouTube Google Trends Collection")
    print(f"Timeframe: {timeframe}")
    print("=" * 70)

    # Load distinct themes from training data
    db = duckdb.connect(str(DB_PATH), read_only=True)
    themes_df = db.execute("""
        SELECT
            li.theme,
            COUNT(*) AS n_sets
        FROM lego_items li
        JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
        WHERE be.annual_growth_pct IS NOT NULL
          AND be.rrp_usd_cents > 0
        GROUP BY li.theme
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC
    """).df()
    db.close()

    print(f"\nFound {len(themes_df)} themes with >= 3 retired sets")
    print()

    # Classify themes
    themes_df["theme_type"] = themes_df["theme"].apply(classify_theme)

    named_count = (themes_df["theme_type"] == "named_ip").sum()
    generic_count = (themes_df["theme_type"] == "generic").sum()
    print(f"Named IPs: {named_count}, Generic: {generic_count}")
    print()

    for _, row in themes_df.iterrows():
        print(f"  {row['theme']:30s} ({row['theme_type']:10s}) -- {row['n_sets']} sets")
    print()

    # Collect GT data
    results: list[dict] = []
    total = len(themes_df)

    for i, (_, row) in enumerate(themes_df.iterrows(), 1):
        theme = row["theme"]
        theme_type = row["theme_type"]
        print(f"[{i}/{total}] {theme} ({theme_type})")

        result = fetch_theme_gt(theme, theme_type, timeframe)
        if result is not None:
            result["n_training_sets"] = int(row["n_sets"])
            results.append(result)

        # Rate limit between requests (skip after last)
        if i < total:
            print(f"  Waiting {REQUEST_DELAY_SECONDS}s...")
            time.sleep(REQUEST_DELAY_SECONDS)

    # Save results
    if results:
        out_df = pd.DataFrame(results)
        out_path = RESULTS_DIR / "theme_gt_summary.csv"
        out_df.to_csv(out_path, index=False)
        print(f"\nSaved {len(results)} themes to {out_path}")
        print()
        print(out_df.to_string(index=False))
    else:
        print("\nNo results collected!")


if __name__ == "__main__":
    main()
