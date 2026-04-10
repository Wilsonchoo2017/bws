'use client';

import { useEffect, useState } from 'react';
import type { CohortRank } from '../types';
import { CohortSection } from '../signals-table';
import { useDetailBundle } from './detail-bundle-context';

interface CohortPanelProps {
  setNumber: string;
}

export function CohortPanel({ setNumber }: CohortPanelProps) {
  const { bundle, loading: bundleLoading } = useDetailBundle();

  const [bl, setBl] = useState<Record<string, CohortRank> | null | undefined>(undefined);
  const [be, setBe] = useState<Record<string, CohortRank> | null | undefined>(undefined);
  const [blLoading, setBlLoading] = useState(true);
  const [beLoading, setBeLoading] = useState(true);

  useEffect(() => {
    if (bundleLoading) return;

    // Use bundle data if present (non-null means cache was warm)
    if (bundle?.signals) {
      const blCohorts = (bundle.signals as Record<string, unknown>)?.cohorts as Record<string, CohortRank> | undefined;
      setBl(blCohorts ?? null);
      setBlLoading(false);
    }
    if (bundle?.signals_be) {
      const beCohorts = (bundle.signals_be as Record<string, unknown>)?.cohorts as Record<string, CohortRank> | undefined;
      setBe(beCohorts ?? null);
      setBeLoading(false);
    }
    // If both came from bundle, done
    if (bundle?.signals && bundle?.signals_be) return;

    // Fetch individually for any missing data
    const controllers: AbortController[] = [];

    if (!bundle?.signals) {
      const blCtrl = new AbortController();
      controllers.push(blCtrl);
      fetch(`/api/items/${setNumber}/signals`, { signal: blCtrl.signal })
        .then((res) => res.json())
        .then((json) => {
          if (json.success && json.data?.cohorts) {
            setBl(json.data.cohorts);
          } else {
            setBl(null);
          }
        })
        .catch((err) => { if (err.name !== 'AbortError') setBl(null); })
        .finally(() => setBlLoading(false));
    }

    if (!bundle?.signals_be) {
      const beCtrl = new AbortController();
      controllers.push(beCtrl);
      fetch(`/api/items/${setNumber}/signals/be`, { signal: beCtrl.signal })
        .then((res) => res.json())
        .then((json) => {
          if (json.success && json.data?.cohorts) {
            setBe(json.data.cohorts);
          } else {
            setBe(null);
          }
        })
        .catch((err) => { if (err.name !== 'AbortError') setBe(null); })
        .finally(() => setBeLoading(false));
    }

    return () => controllers.forEach((c) => c.abort());
  }, [setNumber, bundle, bundleLoading]);

  const bothEmpty = !blLoading && !beLoading && bl == null && be == null;

  if (blLoading && beLoading) {
    return (
      <div className="rounded-lg border px-4 py-6 text-center">
        <p className="text-sm text-muted-foreground">Loading cohort data...</p>
      </div>
    );
  }

  if (bothEmpty) {
    return (
      <div className="rounded-lg border px-4 py-6 text-center">
        <p className="text-sm text-muted-foreground">
          No cohort data available from either source.
        </p>
      </div>
    );
  }

  return (
    <div className="flex gap-4">
      <CohortSource label="BrickLink" data={bl} loading={blLoading} />
      <CohortSource label="Keepa" data={be} loading={beLoading} />
    </div>
  );
}

function CohortSource({
  label,
  data,
  loading,
}: {
  label: string;
  data: Record<string, CohortRank> | null | undefined;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="flex-1 rounded-lg border">
        <div className="bg-muted/50 border-b px-4 py-2">
          <span className="text-xs font-medium">{label}</span>
        </div>
        <div className="px-4 py-6 text-center">
          <p className="text-xs text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (data == null || Object.keys(data).length === 0) {
    return (
      <div className="flex-1 rounded-lg border">
        <div className="bg-muted/50 border-b px-4 py-2">
          <span className="text-xs font-medium">{label}</span>
        </div>
        <div className="px-4 py-6 text-center">
          <p className="text-xs text-muted-foreground">No data available.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1">
      <CohortSection cohorts={data} sourceLabel={label} />
    </div>
  );
}
