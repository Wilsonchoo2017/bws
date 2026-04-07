'use client';

import { useEffect, useState } from 'react';
import type { ItemSignals } from '../types';
import { CohortSection } from '../signals-table';

interface CohortPanelProps {
  setNumber: string;
}

export function CohortPanel({ setNumber }: CohortPanelProps) {
  const [data, setData] = useState<ItemSignals | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/items/${setNumber}/signals`, { signal: controller.signal })
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setData(json.data);
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          // silently degrade - cohort is supplementary info
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [setNumber]);

  if (loading) {
    return (
      <p className="text-sm text-muted-foreground">Loading cohort data...</p>
    );
  }

  if (!data?.cohorts || Object.keys(data.cohorts).length === 0) {
    return (
      <div className="rounded-lg border">
        <div className="bg-muted/50 border-b px-4 py-2">
          <span className="text-xs font-medium">Cohort Rankings</span>
          <span className="text-muted-foreground ml-2 text-xs">
            Percentile rank within peer group
          </span>
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
