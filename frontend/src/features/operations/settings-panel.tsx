'use client';

import { Loader2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { SuppliersManager } from '@/features/settings/suppliers-manager';
import { PlatformsManager } from '@/features/settings/platforms-manager';

interface SettingsData {
  rate_limits: Record<string, { min_delay_ms: number; max_delay_ms: number; max_requests_per_hour: number }>;
  cooldowns: {
    base_cooldown_s: number;
    forbidden_cooldown_s: number;
    max_cooldown_s: number;
    max_continuous_scrape_s: number;
    rest_period_s: number;
  };
  workers: Record<string, { concurrency: number; timeout_s: number }>;
  schedulers: Record<string, { interval_minutes: number; batch_size: number }>;
  dispatcher: { poll_interval_s: number; checkpoint_interval_s: number };
  paused_workers: string[];
  listing: {
    shopee: {
      max_photos: number;
      category: string;
    };
  };
  cart: {
    min_liquidity_score: number;
    deal_threshold_pct: number;
    min_confidence: string;
    max_avoid_probability: number;
    min_growth_pct: number;
  };
}

type Section = keyof SettingsData;

const SECTION_LABELS: Record<string, string> = {
  rate_limits: 'Rate Limits',
  cooldowns: 'Cooldown Thresholds',
  workers: 'Worker Concurrency',
  schedulers: 'Scheduler Intervals',
  dispatcher: 'Dispatcher',
  listing: 'Listing Defaults',
  cart: 'Cart Auto-Scan',
};

const FIELD_LABELS: Record<string, string> = {
  min_delay_ms: 'Min Delay (ms)',
  max_delay_ms: 'Max Delay (ms)',
  max_requests_per_hour: 'Max Requests/Hour',
  base_cooldown_s: 'Base Cooldown (s)',
  forbidden_cooldown_s: '403 Cooldown (s)',
  max_cooldown_s: 'Max Cooldown (s)',
  max_continuous_scrape_s: 'Max Continuous Scrape (s)',
  rest_period_s: 'Rest Period (s)',
  concurrency: 'Workers',
  timeout_s: 'Timeout (s)',
  interval_minutes: 'Interval (min)',
  batch_size: 'Batch Size',
  poll_interval_s: 'Poll Interval (s)',
  checkpoint_interval_s: 'Checkpoint Interval (s)',
  max_photos: 'Max Photos',
  category: 'Category',
  min_liquidity_score: 'Min Liquidity Score',
  deal_threshold_pct: 'Deal Threshold (%)',
  min_confidence: 'Min ML Confidence',
  max_avoid_probability: 'Max Avoid Probability',
  min_growth_pct: 'Min Growth (%)',
};

const SOURCE_LABELS: Record<string, string> = {
  bricklink: 'BrickLink',
  brickeconomy: 'BrickEconomy',
  keepa: 'Keepa',
  bricklink_metadata: 'BrickLink Metadata',
  minifigures: 'Minifigures',
  google_trends: 'Google Trends',
  google_trends_theme: 'Google Trends Theme',
  enrichment: 'Enrichment',
  rescrape: 'Priority Rescrape',
  saturation: 'Shopee Saturation',
  images: 'Image Downloads',
};

export function SettingsPanel() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [defaults, setDefaults] = useState<SettingsData | null>(null);
  const [draft, setDraft] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch('/api/settings');
      const json = await res.json();
      if (json.success) {
        setSettings(json.data);
        setDefaults(json.defaults);
        setDraft(structuredClone(json.data));
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
    fetchSettings();
  }, [fetchSettings]);

  const saveSection = useCallback(
    async (section: Section) => {
      if (!draft) return;
      setSaving(section);
      setSaved(null);
      try {
        const res = await fetch(`/api/settings/${section}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ values: draft[section] }),
        });
        const json = await res.json();
        if (json.success) {
          setSettings((prev) =>
            prev ? { ...prev, [section]: json.data } : prev
          );
          setSaved(section);
          setTimeout(() => setSaved(null), 2000);
        } else {
          setError(json.detail ?? json.error ?? 'Save failed');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Network error');
      } finally {
        setSaving(null);
      }
    },
    [draft]
  );

  const resetSection = useCallback(
    async (section: Section) => {
      setSaving(section);
      try {
        const res = await fetch(`/api/settings/reset/${section}`, {
          method: 'POST',
        });
        const json = await res.json();
        if (json.success) {
          setSettings((prev) =>
            prev ? { ...prev, [section]: json.data } : prev
          );
          setDraft((prev) =>
            prev ? { ...prev, [section]: structuredClone(json.data) } : prev
          );
          setSaved(section);
          setTimeout(() => setSaved(null), 2000);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Network error');
      } finally {
        setSaving(null);
      }
    },
    []
  );

  const updateField = useCallback(
    (section: Section, path: string[], value: number) => {
      setDraft((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let obj: any = next[section];
        for (let i = 0; i < path.length - 1; i++) {
          obj = obj[path[i]];
        }
        obj[path[path.length - 1]] = value;
        return next;
      });
    },
    []
  );

  const updateStringField = useCallback(
    (section: Section, path: string[], value: string) => {
      setDraft((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let obj: any = next[section];
        for (let i = 0; i < path.length - 1; i++) {
          obj = obj[path[i]];
        }
        obj[path[path.length - 1]] = value;
        return next;
      });
    },
    []
  );

  const [pauseLoading, setPauseLoading] = useState<string | null>(null);

  const togglePause = useCallback(
    async (workerKey: string) => {
      if (!settings) return;
      setPauseLoading(workerKey);
      const current = settings.paused_workers ?? [];
      const next = current.includes(workerKey)
        ? current.filter((k) => k !== workerKey)
        : [...current, workerKey];
      try {
        const res = await fetch('/api/settings/paused_workers', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ values: next }),
        });
        const json = await res.json();
        if (json.success) {
          setSettings((prev) =>
            prev ? { ...prev, paused_workers: json.data } : prev
          );
          setDraft((prev) =>
            prev ? { ...prev, paused_workers: json.data } : prev
          );
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Network error');
      } finally {
        setPauseLoading(null);
      }
    },
    [settings]
  );

  const hasChanges = useCallback(
    (section: Section): boolean => {
      if (!settings || !draft) return false;
      return JSON.stringify(settings[section]) !== JSON.stringify(draft[section]);
    },
    [settings, draft]
  );

  const isDefault = useCallback(
    (section: Section): boolean => {
      if (!settings || !defaults) return true;
      return JSON.stringify(settings[section]) === JSON.stringify(defaults[section]);
    },
    [settings, defaults]
  );

  if (loading) {
    return (
      <div className='flex h-32 items-center justify-center'>
        <p className='text-muted-foreground'>Loading settings...</p>
      </div>
    );
  }

  if (error && !settings) {
    return (
      <div className='flex h-32 items-center justify-center'>
        <p className='text-destructive'>{error}</p>
      </div>
    );
  }

  if (!draft || !settings) return null;

  return (
    <div className='flex flex-col gap-6'>
      {/* Suppliers & Platforms */}
      <SuppliersManager />
      <PlatformsManager />

      {error && (
        <div className='rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/20 dark:text-red-400'>
          {error}
          <button
            onClick={() => setError(null)}
            className='ml-2 underline'
          >
            dismiss
          </button>
        </div>
      )}

      {/* Worker Pause/Resume */}
      <div className='rounded-lg border border-border p-4'>
        <h3 className='mb-3 text-sm font-semibold'>Worker Pause / Resume</h3>
        <div className='grid gap-2 sm:grid-cols-2 lg:grid-cols-3'>
          {Object.keys(settings.workers).map((workerKey) => {
            const paused = (settings.paused_workers ?? []).includes(workerKey);
            const isLoading = pauseLoading === workerKey;
            return (
              <button
                key={workerKey}
                disabled={isLoading}
                onClick={() => togglePause(workerKey)}
                className={`flex items-center justify-between rounded border px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${
                  paused
                    ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-900/30 dark:text-red-300'
                    : 'border-green-300 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-900/30 dark:text-green-300'
                }`}
              >
                <span>{SOURCE_LABELS[workerKey] ?? workerKey}</span>
                {isLoading ? (
                  <Loader2 className='size-3.5 animate-spin' />
                ) : (
                  <span className='text-xs'>
                    {paused ? 'PAUSED' : 'RUNNING'}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Rate Limits */}
      <SettingsSection
        title={SECTION_LABELS.rate_limits}
        section='rate_limits'
        hasChanges={hasChanges('rate_limits')}
        isDefault={isDefault('rate_limits')}
        saving={saving === 'rate_limits'}
        saved={saved === 'rate_limits'}
        onSave={() => saveSection('rate_limits')}
        onReset={() => resetSection('rate_limits')}
      >
        <div className='grid gap-4 sm:grid-cols-3'>
          {Object.entries(draft.rate_limits).map(([source, vals]) => (
            <div key={source} className='rounded border border-border p-3'>
              <h4 className='mb-2 text-sm font-medium'>
                {SOURCE_LABELS[source] ?? source}
              </h4>
              {Object.entries(vals).map(([field, val]) => (
                <NumberField
                  key={field}
                  label={FIELD_LABELS[field] ?? field}
                  value={val}
                  onChange={(v) =>
                    updateField('rate_limits', [source, field], v)
                  }
                />
              ))}
            </div>
          ))}
        </div>
      </SettingsSection>

      {/* Cooldowns */}
      <SettingsSection
        title={SECTION_LABELS.cooldowns}
        section='cooldowns'
        hasChanges={hasChanges('cooldowns')}
        isDefault={isDefault('cooldowns')}
        saving={saving === 'cooldowns'}
        saved={saved === 'cooldowns'}
        onSave={() => saveSection('cooldowns')}
        onReset={() => resetSection('cooldowns')}
      >
        <div className='grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3'>
          {Object.entries(draft.cooldowns).map(([field, val]) => (
            <NumberField
              key={field}
              label={FIELD_LABELS[field] ?? field}
              value={val}
              onChange={(v) => updateField('cooldowns', [field], v)}
              suffix={formatSeconds(val)}
            />
          ))}
        </div>
      </SettingsSection>

      {/* Workers */}
      <SettingsSection
        title={SECTION_LABELS.workers}
        section='workers'
        hasChanges={hasChanges('workers')}
        isDefault={isDefault('workers')}
        saving={saving === 'workers'}
        saved={saved === 'workers'}
        onSave={() => saveSection('workers')}
        onReset={() => resetSection('workers')}
      >
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
          {Object.entries(draft.workers).map(([source, vals]) => (
            <div key={source} className='rounded border border-border p-3'>
              <h4 className='mb-2 text-sm font-medium'>
                {SOURCE_LABELS[source] ?? source}
              </h4>
              {Object.entries(vals).map(([field, val]) => (
                <NumberField
                  key={field}
                  label={FIELD_LABELS[field] ?? field}
                  value={val}
                  onChange={(v) =>
                    updateField('workers', [source, field], v)
                  }
                />
              ))}
            </div>
          ))}
        </div>
      </SettingsSection>

      {/* Schedulers */}
      <SettingsSection
        title={SECTION_LABELS.schedulers}
        section='schedulers'
        hasChanges={hasChanges('schedulers')}
        isDefault={isDefault('schedulers')}
        saving={saving === 'schedulers'}
        saved={saved === 'schedulers'}
        onSave={() => saveSection('schedulers')}
        onReset={() => resetSection('schedulers')}
      >
        <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
          {Object.entries(draft.schedulers).map(([source, vals]) => (
            <div key={source} className='rounded border border-border p-3'>
              <h4 className='mb-2 text-sm font-medium'>
                {SOURCE_LABELS[source] ?? source}
              </h4>
              {Object.entries(vals).map(([field, val]) => (
                <NumberField
                  key={field}
                  label={FIELD_LABELS[field] ?? field}
                  value={val}
                  onChange={(v) =>
                    updateField('schedulers', [source, field], v)
                  }
                />
              ))}
            </div>
          ))}
        </div>
      </SettingsSection>

      {/* Dispatcher */}
      <SettingsSection
        title={SECTION_LABELS.dispatcher}
        section='dispatcher'
        hasChanges={hasChanges('dispatcher')}
        isDefault={isDefault('dispatcher')}
        saving={saving === 'dispatcher'}
        saved={saved === 'dispatcher'}
        onSave={() => saveSection('dispatcher')}
        onReset={() => resetSection('dispatcher')}
      >
        <div className='grid gap-x-6 gap-y-1 sm:grid-cols-2'>
          {Object.entries(draft.dispatcher).map(([field, val]) => (
            <NumberField
              key={field}
              label={FIELD_LABELS[field] ?? field}
              value={val}
              onChange={(v) => updateField('dispatcher', [field], v)}
            />
          ))}
        </div>
      </SettingsSection>

      {/* Listing Defaults */}
      <SettingsSection
        title={SECTION_LABELS.listing}
        section='listing'
        hasChanges={hasChanges('listing')}
        isDefault={isDefault('listing')}
        saving={saving === 'listing'}
        saved={saved === 'listing'}
        onSave={() => saveSection('listing')}
        onReset={() => resetSection('listing')}
      >
        <div className='rounded border border-border p-3'>
          <h4 className='mb-2 text-sm font-medium'>Shopee</h4>
          <NumberField
            label={FIELD_LABELS.max_photos}
            value={draft.listing.shopee.max_photos}
            onChange={(v) =>
              updateField('listing', ['shopee', 'max_photos'], v)
            }
          />
          <TextField
            label={FIELD_LABELS.category}
            value={draft.listing.shopee.category}
            onChange={(v) =>
              updateStringField('listing', ['shopee', 'category'], v)
            }
          />
        </div>
      </SettingsSection>

      {/* Cart Auto-Scan */}
      <SettingsSection
        title={SECTION_LABELS.cart}
        section='cart'
        hasChanges={hasChanges('cart')}
        isDefault={isDefault('cart')}
        saving={saving === 'cart'}
        saved={saved === 'cart'}
        onSave={() => saveSection('cart')}
        onReset={() => resetSection('cart')}
      >
        <div className='grid gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3'>
          <NumberField
            label={FIELD_LABELS.min_liquidity_score}
            value={draft.cart.min_liquidity_score}
            onChange={(v) => updateField('cart', ['min_liquidity_score'], v)}
          />
          <NumberField
            label={FIELD_LABELS.deal_threshold_pct}
            value={draft.cart.deal_threshold_pct}
            onChange={(v) => updateField('cart', ['deal_threshold_pct'], v)}
          />
          <TextField
            label={FIELD_LABELS.min_confidence}
            value={draft.cart.min_confidence}
            onChange={(v) => updateStringField('cart', ['min_confidence'], v)}
          />
          <NumberField
            label={FIELD_LABELS.max_avoid_probability}
            value={draft.cart.max_avoid_probability}
            onChange={(v) => updateField('cart', ['max_avoid_probability'], v)}
          />
          <NumberField
            label={FIELD_LABELS.min_growth_pct}
            value={draft.cart.min_growth_pct}
            onChange={(v) => updateField('cart', ['min_growth_pct'], v)}
          />
        </div>
      </SettingsSection>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SettingsSection({
  title,
  section,
  hasChanges,
  isDefault,
  saving,
  saved,
  onSave,
  onReset,
  children,
}: {
  readonly title: string;
  readonly section: string;
  readonly hasChanges: boolean;
  readonly isDefault: boolean;
  readonly saving: boolean;
  readonly saved: boolean;
  readonly onSave: () => void;
  readonly onReset: () => void;
  readonly children: React.ReactNode;
}) {
  return (
    <div className='rounded-lg border border-border p-4'>
      <div className='mb-3 flex items-center justify-between'>
        <h3 className='text-sm font-semibold'>{title}</h3>
        <div className='flex items-center gap-2'>
          {saved && (
            <span className='text-xs text-green-600 dark:text-green-400'>
              Saved
            </span>
          )}
          {!isDefault && (
            <Button
              variant='ghost'
              size='sm'
              onClick={onReset}
              disabled={saving}
              className='h-7 px-2 text-xs'
            >
              Reset to defaults
            </Button>
          )}
          <Button
            variant={hasChanges ? 'default' : 'outline'}
            size='sm'
            onClick={onSave}
            disabled={!hasChanges || saving}
            className='h-7 px-3 text-xs'
          >
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>
      {children}
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  suffix,
}: {
  readonly label: string;
  readonly value: number;
  readonly onChange: (v: number) => void;
  readonly suffix?: string;
}) {
  return (
    <div className='flex items-center justify-between gap-2 py-1'>
      <label className='text-muted-foreground text-xs whitespace-nowrap'>
        {label}
      </label>
      <div className='flex items-center gap-1.5'>
        <input
          type='number'
          value={value}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (!Number.isNaN(n) && n >= 0) onChange(n);
          }}
          className='border-border bg-background h-7 w-24 rounded border px-2 text-right font-mono text-xs'
        />
        {suffix && (
          <span className='text-muted-foreground text-xs'>{suffix}</span>
        )}
      </div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (v: string) => void;
}) {
  return (
    <div className='flex items-center justify-between gap-2 py-1'>
      <label className='text-muted-foreground text-xs whitespace-nowrap'>
        {label}
      </label>
      <input
        type='text'
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className='border-border bg-background h-7 w-48 rounded border px-2 text-right text-xs'
      />
    </div>
  );
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}
