'use client';

import { useEffect, useState } from 'react';
import type { CoverageData, SourceCoverage } from './types';

const SOURCE_LABELS: Record<string, string> = {
  bricklink: 'BrickLink',
  brickeconomy: 'Brick Economy',
  keepa: 'Keepa (Amazon)',
  shopee: 'Shopee',
  mightyutan: 'Mighty Utan',
  toysrus: 'Toys R Us',
  google_trends: 'Google Trends',
  minifigures: 'Minifigures',
  images: 'Images',
  ml_predictions: 'ML Predictions',
};

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

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

export function DataCoverage() {
  const [data, setData] = useState<CoverageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/stats/coverage')
      .then((r) => r.json())
      .then((json) => {
        if (json.success) {
          setData(json.data);
        } else {
          setError(json.error ?? 'Failed to load');
        }
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Network error')
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-muted-foreground'>Loading coverage stats...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className='flex h-96 items-center justify-center'>
        <p className='text-destructive'>{error ?? 'No data'}</p>
      </div>
    );
  }

  const sorted = [...data.sources].sort(
    (a, b) => b.coverage_pct - a.coverage_pct
  );

  return (
    <div className='flex flex-col gap-6'>
      <div>
        <h1 className='text-2xl font-bold'>Data Coverage</h1>
        <p className='text-muted-foreground text-sm'>
          {data.total_sets} tracked sets across {data.sources.length} sources
        </p>
      </div>

      {/* Summary cards */}
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

      {/* Coverage table */}
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
      {sub && (
        <p className='text-muted-foreground text-xs'>{sub}</p>
      )}
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
      <td className={`px-4 py-2.5 text-right font-mono ${coverageColor(pct)}`}>
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
        {source.latest_scraped ? formatRelative(source.latest_scraped) : '-'}
      </td>
    </tr>
  );
}
