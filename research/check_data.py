"""
Quick data inventory check. Run anytime with:
  .venv/bin/python research/check_data.py
"""

import json
from pathlib import Path

import duckdb

DB_PATH = Path.home() / ".bws" / "bws.duckdb"
db = duckdb.connect(str(DB_PATH), read_only=True)

print("=== DATA INVENTORY ===\n")

# Table counts
tables = [
    "lego_items", "brickeconomy_snapshots", "keepa_snapshots",
    "google_trends_snapshots", "bricklink_price_history", "shopee_saturation",
]
for t in tables:
    try:
        n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:30s} {n:5d}")
    except Exception:
        print(f"  {t:30s}   N/A")

# Items breakdown
r = db.execute("""
    SELECT COUNT(*),
           SUM(CASE WHEN year_retired IS NOT NULL THEN 1 ELSE 0 END),
           SUM(CASE WHEN retiring_soon THEN 1 ELSE 0 END)
    FROM lego_items
""").fetchone()
print(f"\n  Items: {r[0]} total, {r[1]} retired, {r[2]} retiring_soon")

# BE completeness
r = db.execute("""
    SELECT COUNT(*),
           SUM(CASE WHEN annual_growth_pct IS NOT NULL THEN 1 ELSE 0 END),
           SUM(CASE WHEN rrp_usd_cents > 0 THEN 1 ELSE 0 END),
           SUM(CASE WHEN annual_growth_pct IS NOT NULL AND rrp_usd_cents > 0 THEN 1 ELSE 0 END)
    FROM brickeconomy_snapshots
""").fetchone()
print(f"\n  BE: {r[0]} total, {r[1]} with growth, {r[2]} with RRP, {r[3]} with both")

# Candlestick
rows = db.execute("SELECT candlestick_json FROM brickeconomy_snapshots WHERE candlestick_json IS NOT NULL").fetchall()
lens = []
for row in rows:
    cs = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    if isinstance(cs, list):
        lens.append(len(cs))
print(f"  Candlestick: {len(lens)} sets, >=6m: {sum(1 for l in lens if l >= 6)}, >=12m: {sum(1 for l in lens if l >= 12)}, >=24m: {sum(1 for l in lens if l >= 24)}")

# Keepa with Amazon history
rows = db.execute("SELECT amazon_price_json FROM keepa_snapshots WHERE amazon_price_json IS NOT NULL").fetchall()
long_amz = sum(1 for row in rows for d in [json.loads(row[0]) if isinstance(row[0], str) else row[0]] if isinstance(d, list) and len(d) >= 10)
print(f"  Keepa with Amazon history (>=10pts): {long_amz}")

# Overlaps
pairs = [
    ("BE + BL", "SELECT COUNT(DISTINCT be.set_number) FROM brickeconomy_snapshots be JOIN bricklink_price_history bp ON (be.set_number || '-1') = bp.item_id"),
    ("BE + Keepa", "SELECT COUNT(DISTINCT be.set_number) FROM brickeconomy_snapshots be JOIN keepa_snapshots ks ON be.set_number = ks.set_number"),
    ("BE + BL + Keepa", "SELECT COUNT(DISTINCT be.set_number) FROM brickeconomy_snapshots be JOIN bricklink_price_history bp ON (be.set_number || '-1') = bp.item_id JOIN keepa_snapshots ks ON be.set_number = ks.set_number"),
]
print()
for label, q in pairs:
    n = db.execute(q).fetchone()[0]
    print(f"  {label:20s} {n:5d}")

# Theme distribution (BE with growth+RRP)
print("\n  Top themes (BE with growth+RRP):")
rows = db.execute("""
    SELECT li.theme, COUNT(*), AVG(be.annual_growth_pct)
    FROM lego_items li
    JOIN brickeconomy_snapshots be ON li.set_number = be.set_number
    WHERE be.annual_growth_pct IS NOT NULL AND be.rrp_usd_cents > 0
    GROUP BY li.theme ORDER BY COUNT(*) DESC LIMIT 15
""").fetchall()
for r in rows:
    print(f"    {str(r[0]):25s} {r[1]:3d} sets  avg={r[2]:.1f}%")

db.close()
print("\nDone.")
