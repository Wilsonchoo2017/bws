'use client';

import { useEffect, useState } from 'react';
import { useDetailBundle, type ScrapeHistoryEntry } from './detail-bundle-context';

const SOURCE_LABELS: Record<string, string> = {
  bricklink_prices: 'BrickLink Prices',
  bricklink_sales: 'BrickLink Sales',
  bricklink_sellers: 'BrickLink Sellers',
  brickeconomy: 'BrickEconomy',
  keepa: 'Keepa',
  shopee_saturation: 'Shopee Saturation',
  shopee_competition: 'Shopee Competition',
  minifigures: 'Minifigures',
  ml_prediction: 'ML Prediction',
  google_trends: 'Google Trends',
  'task:bricklink_metadata': 'Task: BrickLink',
  'task:brickeconomy': 'Task: BrickEconomy',
  'task:keepa': 'Task: Keepa',
  'task:minifigures': 'Task: Minifigures',
  'task:google_trends': 'Task: Google Trends',
  'task:google_trends_theme': 'Task: Trends (Theme)',
};

const SOURCE_COLORS: Record<string, string> = {
  bricklink_prices: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  bricklink_sales: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  bricklink_sellers: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  brickeconomy: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
  keepa: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  shopee_saturation: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  shopee_competition: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  minifigures: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  ml_prediction: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
  google_trends: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300',
};

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-green-600 dark:text-green-400',
  failed: 'text-red-600 dark:text-red-400',
  running: 'text-yellow-600 dark:text-yellow-400',
  pending: 'text-muted-foreground',
  blocked: 'text-muted-foreground',
};

function getSourceColor(source: string): string {
  if (SOURCE_COLORS[source]) return SOURCE_COLORS[source];
  const base = source.replace(/^task:/, '');
  if (SOURCE_COLORS[base]) return SOURCE_COLORS[base];
  return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300';
}

function formatLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, ' ').replace(/^task:/, 'Task: ');
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function relativeTime(ts: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '';
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return `${Math.floor(diffDays / 30)}mo ago`;
}

interface ScrapeHistoryPanelProps {
  setNumber: string;
}

export function ScrapeHistoryPanel({ setNumber }: ScrapeHistoryPanelProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [entries, setEntries] = useState<ScrapeHistoryEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (bundleLoading) return;

    if (bundle?.scrape_history) {
      setEntries(bundle.scrape_history);
      setLoading(false);
      return;
    }

    const ctrl = new AbortController();
    fetch(`/api/items/${setNumber}/scrape-history`, { signal: ctrl.signal })
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setEntries(json.data);
        } else {
          setEntries([]);
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setEntries([]);
      })
      .finally(() => setLoading(false));

    return () => ctrl.abort();
  }, [setNumber, bundle, bundleLoading]);

  if (loading) {
    return (
      <div>
        <h2 className="mb-3 text-lg font-semibold">Scrape History</h2>
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    );
  }

  if (!entries || entries.length === 0) {
    return (
      <div>
        <h2 className="mb-3 text-lg font-semibold">Scrape History</h2>
        <p className="text-muted-foreground text-sm">No scrape history yet.</p>
      </div>
    );
  }

  // Compute unique sources for filter buttons
  const sources = [...new Set(entries.map((e) => e.source))].sort();

  // Compute per-source latest timestamp
  const latestBySource: Record<string, string> = {};
  for (const entry of entries) {
    if (!latestBySource[entry.source]) {
      latestBySource[entry.source] = entry.scraped_at;
    }
  }

  const filtered = filter ? entries.filter((e) => e.source === filter) : entries;
  const displayed = expanded ? filtered : filtered.slice(0, 30);

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold">Scrape History</h2>

      {/* Summary: latest per source */}
      <div className="mb-3 flex flex-wrap gap-2">
        {sources.map((src) => {
          const isActive = filter === src;
          const isTask = src.startsWith('task:');
          return (
            <button
              key={src}
              onClick={() => setFilter(isActive ? null : src)}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-all ${
                isActive
                  ? `${getSourceColor(src)} border-current`
                  : 'border-border text-muted-foreground hover:border-foreground/30'
              }`}
            >
              {formatLabel(src)}
              {!isTask && (
                <span className="ml-1 opacity-60">
                  {relativeTime(latestBySource[src])}
                </span>
              )}
            </button>
          );
        })}
        {filter && (
          <button
            onClick={() => setFilter(null)}
            className="rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground hover:border-foreground/30"
          >
            Clear filter
          </button>
        )}
      </div>

      {/* Timeline table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="px-3 py-2 text-left font-medium">Source</th>
              <th className="px-3 py-2 text-left font-medium">Scraped At</th>
              <th className="px-3 py-2 text-left font-medium">Age</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {displayed.map((entry, i) => {
              const isTask = entry.source.startsWith('task:');
              return (
                <tr
                  key={`${entry.source}-${entry.scraped_at}-${i}`}
                  className="border-b border-border last:border-0 hover:bg-muted/30"
                >
                  <td className="px-3 py-1.5">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${getSourceColor(entry.source)}`}
                    >
                      {formatLabel(entry.source)}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {formatTimestamp(entry.scraped_at)}
                  </td>
                  <td className="px-3 py-1.5 text-xs text-muted-foreground">
                    {relativeTime(entry.scraped_at)}
                  </td>
                  <td className="px-3 py-1.5 text-xs">
                    {isTask && entry.status ? (
                      <span className={STATUS_COLORS[entry.status] ?? ''}>
                        {entry.status}
                        {entry.error && (
                          <span className="ml-1 text-red-500" title={entry.error}>
                            - {entry.error.slice(0, 60)}
                            {entry.error.length > 60 ? '...' : ''}
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-green-600 dark:text-green-400">ok</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {filtered.length > 30 && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground"
        >
          Show all {filtered.length} entries
        </button>
      )}
      {expanded && filtered.length > 30 && (
        <button
          onClick={() => setExpanded(false)}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground"
        >
          Collapse
        </button>
      )}

      <p className="mt-2 text-xs text-muted-foreground">
        {entries.length} total scrape events across {sources.length} sources
      </p>
    </div>
  );
}
