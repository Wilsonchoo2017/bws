'use client';

import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';

interface ModelStats {
  n_train?: number;
  regressor_cv_r2?: number;
  regressor_features?: number;
  classifier_auc?: number;
  classifier_recall?: number;
  n_avoid?: number;
}

interface PredictionSummary {
  total: number;
  buy: number;
  hold: number;
  avoid: number;
  avg_growth: number;
}

export function MLPanel() {
  const [training, setTraining] = useState(false);
  const [result, setResult] = useState<ModelStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PredictionSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await fetch('/api/ml/growth/predictions');
      const json = await res.json();
      if (Array.isArray(json)) {
        const preds = json;
        const buy = preds.filter((p: Record<string, unknown>) => p.buy_signal === true).length;
        const avoid = preds.filter((p: Record<string, unknown>) => p.avoid === true).length;
        const hold = preds.length - buy - avoid;
        const growths = preds
          .map((p: Record<string, unknown>) => p.growth_pct as number)
          .filter((g: number) => g != null && !Number.isNaN(g));
        const avg = growths.length > 0 ? growths.reduce((a: number, b: number) => a + b, 0) / growths.length : 0;
        setSummary({ total: preds.length, buy, hold, avoid, avg_growth: avg });
      }
    } catch {
      // ignore
    } finally {
      setLoadingSummary(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const handleRetrain = async () => {
    setTraining(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch('/api/ml/growth/retrain', { method: 'POST' });
      const json = await res.json();
      if (json.status === 'retrained') {
        setResult(json);
        await fetchSummary();
      } else {
        setError(json.error ?? 'Retrain failed');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setTraining(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Retrain section */}
      <div className="rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold">Train ML Model</h3>
            <p className="text-sm text-muted-foreground">
              Runs Optuna hyperparameter tuning + trains regressor and classifier. Takes ~10 minutes.
            </p>
          </div>
          <Button
            onClick={handleRetrain}
            disabled={training}
            variant={training ? 'outline' : 'default'}
          >
            {training ? (
              <span className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Training...
              </span>
            ) : (
              'Train Model'
            )}
          </Button>
        </div>

        {error && (
          <div className="mt-3 rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-3 rounded bg-emerald-50 p-3 dark:bg-emerald-900/20">
            <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
              Training complete
            </p>
            <div className="mt-2 grid grid-cols-2 gap-x-8 gap-y-1 text-sm">
              <div className="text-muted-foreground">Training sets</div>
              <div className="font-mono">{result.n_train?.toLocaleString()}</div>
              <div className="text-muted-foreground">Regressor CV R2</div>
              <div className="font-mono">{result.regressor_cv_r2?.toFixed(3)}</div>
              <div className="text-muted-foreground">Features</div>
              <div className="font-mono">{result.regressor_features}</div>
              {result.classifier_auc != null && (
                <>
                  <div className="text-muted-foreground">Classifier AUC</div>
                  <div className="font-mono">{result.classifier_auc.toFixed(3)}</div>
                  <div className="text-muted-foreground">Classifier Recall</div>
                  <div className="font-mono">{result.classifier_recall?.toFixed(3)}</div>
                  <div className="text-muted-foreground">Sets flagged avoid</div>
                  <div className="font-mono">{result.n_avoid}</div>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Current predictions summary */}
      <div className="rounded-lg border border-border p-4">
        <h3 className="font-semibold">Current Predictions</h3>
        {loadingSummary ? (
          <p className="mt-2 text-sm text-muted-foreground">Loading...</p>
        ) : summary ? (
          <div className="mt-3 grid grid-cols-4 gap-4">
            <div className="rounded-lg bg-muted/50 p-3 text-center">
              <div className="text-2xl font-bold">{summary.total}</div>
              <div className="text-xs text-muted-foreground">Total Sets</div>
            </div>
            <div className="rounded-lg bg-emerald-50 p-3 text-center dark:bg-emerald-900/20">
              <div className="text-2xl font-bold text-emerald-700 dark:text-emerald-300">{summary.buy}</div>
              <div className="text-xs text-muted-foreground">BUY</div>
            </div>
            <div className="rounded-lg bg-yellow-50 p-3 text-center dark:bg-yellow-900/20">
              <div className="text-2xl font-bold text-yellow-700 dark:text-yellow-300">{summary.hold}</div>
              <div className="text-xs text-muted-foreground">HOLD</div>
            </div>
            <div className="rounded-lg bg-red-50 p-3 text-center dark:bg-red-900/20">
              <div className="text-2xl font-bold text-red-700 dark:text-red-300">{summary.avoid}</div>
              <div className="text-xs text-muted-foreground">AVOID</div>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">No predictions loaded. Train a model first.</p>
        )}
        {summary && (
          <p className="mt-2 text-sm text-muted-foreground">
            Average predicted growth: +{summary.avg_growth.toFixed(1)}%
          </p>
        )}
      </div>
    </div>
  );
}
