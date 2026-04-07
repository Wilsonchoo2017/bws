'use client';

import { RefreshCwIcon } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { ItemSignals } from '../types';
import { CohortSection } from '../signals-table';

interface CohortPanelProps {
  setNumber: string;
}

export function CohortPanel({ setNumber }: CohortPanelProps) {
  const [data, setData] = useState<ItemSignals | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchSignals = (signal?: AbortSignal) => {
    return fetch(`/api/items/${setNumber}/signals`, { signal })
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setData(json.data);
        }
      });
  };

  useEffect(() => {
    const controller = new AbortController();
    fetchSignals(controller.signal)
      .catch((err) => {
        if (err.name !== 'AbortError') {
          // silently degrade - cohort is supplementary info
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [setNumber]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchSignals()
      .catch(() => {})
      .finally(() => setRefreshing(false));
  };

  if (loading) {
    return (
      <p className="text-sm text-muted-foreground">Loading cohort data...</p>
    );
  }

  if (!data?.cohorts || Object.keys(data.cohorts).length === 0) {
    return (
      <div className="rounded-lg border">
        <div className="bg-muted/50 border-b px-4 py-2 flex items-center justify-between">
          <div>
            <span className="text-xs font-medium">Cohort Rankings</span>
            <span className="text-muted-foreground ml-2 text-xs">
              Percentile rank within peer group
            </span>
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
          >
            <RefreshCwIcon className={`size-3 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing...' : 'Refresh Signals'}
          </button>
        </div>
        <div className="px-4 py-6 text-center">
          <p className="text-sm text-muted-foreground">
            No cohort data available. Requires BrickLink sales history and at least 3 peer items.
          </p>
        </div>
      </div>
    );
  }

  return <CohortSection cohorts={data.cohorts} />;
}
