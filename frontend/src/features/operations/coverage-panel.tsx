'use client';

import { useCallback, useEffect, useState } from 'react';
import type {
  CoverageData,
  SetCoverageData,
  SetCoverageRow,
  SourceCoverage,
} from './types';
import { formatRelativeTime } from './types';

const SOURCE_LABELS: Record<string, string> = {
  bricklink: 'BrickLink',
  brickeconomy: 'Brick Economy',
  keepa: 'Keepa (Amazon)',
  minifigures: 'Minifigures',
};

const SHORT_LABELS: Record<string, string> = {
  bricklink: 'BL',
  brickeconomy: 'BE',
  keepa: 'Keepa',
  minifigures: 'Minifig',
};

type CoverageFilter = 'all' | 'complete' | 'partial' | 'missing';

function coverageColor(pct: number): string {
  if (pct >= 80) return 'text-green-600 dark:text-green-400';
  if (pct >= 50) return 'text-yellow-600 dark:text-yellow-400';
  return 'text-red-600 dark:text-red-400';
}

function barColor(pct: number): string {
  if (pct >= 80) return 'bg-green-500';
  if (pct >= 50) return 'bg-yellow-500';
  return 'bg-red-500';
}

export function CoveragePanel() {
  const [view, setView] = useState<'sources' | 'sets'>('sets');

  return (
    <div className='flex flex-col gap-4'>
      <div className='flex gap-1 rounded-lg border p-1 self-start'>
        <button
          onClick={() => setView('sets')}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            view === 'sets'
              ? 'bg-primary text-primary-foreground'
              : 'hover:bg-muted'
          }`}
        >
          By Set
        </button>
        <button
          onClick={() => setView('sources')}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            view === 'sources'
              ? 'bg-primary text-primary-foreground'
              : 'hover:bg-muted'
          }`}
        >
          By Source
        </button>
      </div>

      {view === 'sources' ? <SourcesView /> : <SetsView />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sources view (original)
// ---------------------------------------------------------------------------

function SourcesView() {
  const [data, setData] = useState<CoverageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCoverage = useCallback(async () => {
    try {
      const res = await fetch('/api/stats/coverage');
      const json = await res.json();
      if (json.success) {
        setData(json.data);
        setError(null);
      } else {
        setError(json.error ?? 'Failed to load');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCoverage();
  }, [fetchCoverage]);

  if (loading) {
    return <LoadingState />;
  }

  if (error || !data) {
    return <ErrorState message={error} />;
  }

  const sorted = [...data.sources].sort(
    (a, b) => b.coverage_pct - a.coverage_pct,
  );

  return (
    <div className='flex flex-col gap-6'>
      <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
        <SummaryCard
          label='Total Sets'
          value={data.total_sets.toLocaleString()}
        />
        <SummaryCard
          label='Full Coverage'
          value={sorted.filter((s) => s.coverage_pct >= 80).length.toString()}
          sub={`of ${sorted.length} sources`}
        />
        <SummaryCard
          label='Most Data'
          value={SOURCE_LABELS[sorted[0]?.source] ?? '-'}
          sub={`${sorted[0]?.coverage_pct ?? 0}%`}
        />
        <SummaryCard
          label='Total Rows'
          value={data.sources
            .reduce((sum, s) => sum + s.total_rows, 0)
            .toLocaleString()}
          sub='all sources'
        />
      </div>

      <div className='overflow-auto rounded border'>
        <table className='w-full text-sm'>
          <thead className='bg-muted/50 sticky top-0'>
            <tr>
              <th className='px-4 py-2.5 text-left font-medium'>Source</th>
              <th className='px-4 py-2.5 text-right font-medium'>Coverage</th>
              <th className='w-48 px-4 py-2.5 font-medium'>
                <span className='sr-only'>Bar</span>
              </th>
              <th className='px-4 py-2.5 text-right font-medium'>Sets</th>
              <th className='px-4 py-2.5 text-right font-medium'>Missing</th>
              <th className='px-4 py-2.5 text-right font-medium'>Rows</th>
              <th className='px-4 py-2.5 text-left font-medium'>
                Last Scraped
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((source) => (
              <SourceRow
                key={source.source}
                source={source}
                totalSets={data.total_sets}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sets view (new)
// ---------------------------------------------------------------------------

function SetsView() {
  const [data, setData] = useState<SetCoverageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<CoverageFilter>('all');
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(1);

  const fetchSets = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        filter,
        page: String(page),
        page_size: '50',
      });
      if (search) params.set('search', search);

      const res = await fetch(`/api/stats/coverage/sets?${params}`);
      const json = await res.json();
      if (json.success) {
        setData(json.data);
        setError(null);
      } else {
        setError(json.error ?? 'Failed to load');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setLoading(false);
    }
  }, [filter, search, page]);

  useEffect(() => {
    fetchSets();
  }, [fetchSets]);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleFilterChange = (f: CoverageFilter) => {
    setFilter(f);
    setPage(1);
  };

  if (error && !data) {
    return <ErrorState message={error} />;
  }

  const totalPages = data ? Math.ceil(data.total_count / data.page_size) : 0;

  return (
    <div className='flex flex-col gap-4'>
      {/* Distribution summary */}
      {data?.distribution && (
        <div className='grid grid-cols-2 gap-3 sm:grid-cols-5'>
          {Array.from({ length: (data.total_sources ?? 0) + 1 }, (_, i) => (
            <button
              key={i}
              onClick={() =>
                handleFilterChange(
                  i === 0
                    ? 'missing'
                    : i === data.total_sources
                      ? 'complete'
                      : 'partial',
                )
              }
              className={`rounded-lg border px-3 py-2 text-left transition-colors hover:bg-muted/50 ${
                (filter === 'missing' && i === 0) ||
                (filter === 'complete' && i === data.total_sources) ||
                (filter === 'partial' &&
                  i > 0 &&
                  i < data.total_sources)
                  ? 'ring-primary ring-2'
                  : ''
              }`}
            >
              <p className='text-muted-foreground text-xs'>
                {i === 0
                  ? 'No data'
                  : i === data.total_sources
                    ? 'Complete'
                    : `${i}/${data.total_sources}`}
              </p>
              <p className='text-lg font-bold'>
                {(data.distribution[i] ?? 0).toLocaleString()}
              </p>
            </button>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className='flex flex-wrap items-center gap-3'>
        <input
          type='text'
          placeholder='Search set number or title...'
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className='border-input bg-background placeholder:text-muted-foreground rounded-md border px-3 py-1.5 text-sm'
        />
        <div className='flex gap-1'>
          {(
            [
              ['all', 'All'],
              ['complete', 'Complete'],
              ['partial', 'Partial'],
              ['missing', 'No Data'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => handleFilterChange(key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                filter === key
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted hover:bg-muted/80'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {data && (
          <span className='text-muted-foreground text-xs'>
            {data.total_count.toLocaleString()} sets
          </span>
        )}
      </div>

      {/* Table */}
      {loading && !data ? (
        <LoadingState />
      ) : data ? (
        <div className='overflow-auto rounded border'>
          <table className='w-full text-sm'>
            <thead className='bg-muted/50 sticky top-0'>
              <tr>
                <th className='px-4 py-2.5 text-left font-medium'>Set</th>
                <th className='px-4 py-2.5 text-left font-medium'>Title</th>
                {data.source_labels.map((src) => (
                  <th
                    key={src}
                    className='px-3 py-2.5 text-center font-medium'
                  >
                    {SHORT_LABELS[src] ?? src}
                  </th>
                ))}
                <th className='px-3 py-2.5 text-center font-medium'>
                  Coverage
                </th>
              </tr>
            </thead>
            <tbody>
              {data.sets.map((row) => (
                <SetRow
                  key={row.set_number}
                  row={row}
                  sourceLabels={data.source_labels}
                />
              ))}
              {data.sets.length === 0 && (
                <tr>
                  <td
                    colSpan={data.source_labels.length + 3}
                    className='text-muted-foreground px-4 py-8 text-center'
                  >
                    No sets found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className='flex items-center justify-between'>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className='rounded-md border px-3 py-1.5 text-sm disabled:opacity-40'
          >
            Previous
          </button>
          <span className='text-muted-foreground text-sm'>
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className='rounded-md border px-3 py-1.5 text-sm disabled:opacity-40'
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared components
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <div className='flex h-64 items-center justify-center'>
      <p className='text-muted-foreground'>Loading coverage stats...</p>
    </div>
  );
}

function ErrorState({ message }: { message: string | null }) {
  return (
    <div className='flex h-64 items-center justify-center'>
      <p className='text-destructive'>{message ?? 'No data'}</p>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className='rounded-lg border px-4 py-3'>
      <p className='text-muted-foreground text-xs font-medium uppercase'>
        {label}
      </p>
      <p className='mt-1 text-xl font-bold'>{value}</p>
      {sub && <p className='text-muted-foreground text-xs'>{sub}</p>}
    </div>
  );
}

function SourceRow({
  source,
  totalSets,
}: {
  source: SourceCoverage;
  totalSets: number;
}) {
  const label = SOURCE_LABELS[source.source] ?? source.source;
  const pct = source.coverage_pct;

  return (
    <tr className='border-border border-t'>
      <td className='px-4 py-2.5 font-medium'>{label}</td>
      <td
        className={`px-4 py-2.5 text-right font-mono ${coverageColor(pct)}`}
      >
        {pct}%
      </td>
      <td className='px-4 py-2.5'>
        <div className='bg-muted h-2 w-full overflow-hidden rounded-full'>
          <div
            className={`h-full rounded-full transition-all ${barColor(pct)}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </td>
      <td className='px-4 py-2.5 text-right font-mono'>
        {source.distinct_sets.toLocaleString()}
        <span className='text-muted-foreground'>
          /{totalSets.toLocaleString()}
        </span>
      </td>
      <td className='px-4 py-2.5 text-right font-mono'>
        {source.missing_sets > 0 ? (
          <span className='text-red-600 dark:text-red-400'>
            {source.missing_sets.toLocaleString()}
          </span>
        ) : (
          <span className='text-green-600 dark:text-green-400'>0</span>
        )}
      </td>
      <td className='text-muted-foreground px-4 py-2.5 text-right font-mono'>
        {source.total_rows.toLocaleString()}
      </td>
      <td className='text-muted-foreground px-4 py-2.5 text-xs'>
        {source.latest_scraped
          ? formatRelativeTime(source.latest_scraped)
          : '-'}
      </td>
    </tr>
  );
}

function SetRow({
  row,
  sourceLabels,
}: {
  row: SetCoverageRow;
  sourceLabels: string[];
}) {
  const pct = Math.round((row.covered_count / row.total_sources) * 100);

  return (
    <tr className='border-border border-t'>
      <td className='px-4 py-2 font-mono text-xs'>{row.set_number}</td>
      <td className='max-w-[200px] truncate px-4 py-2 text-xs'>
        {row.title ?? '-'}
      </td>
      {sourceLabels.map((src) => {
        const status = row.sources[src];
        return (
          <td key={src} className='px-3 py-2 text-center'>
            {status?.covered ? (
              <span
                className='text-green-600 dark:text-green-400'
                title={
                  status.latest
                    ? formatRelativeTime(status.latest)
                    : undefined
                }
              >
                *
              </span>
            ) : (
              <span className='text-red-400 dark:text-red-500'>-</span>
            )}
          </td>
        );
      })}
      <td className='px-3 py-2 text-center'>
        <span
          className={`text-xs font-medium ${coverageColor(pct)}`}
        >
          {row.covered_count}/{row.total_sources}
        </span>
      </td>
    </tr>
  );
}
