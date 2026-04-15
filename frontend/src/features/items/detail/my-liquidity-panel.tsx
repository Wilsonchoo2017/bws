'use client';

import { useEffect, useMemo, useState } from 'react';
import { scoreBg, scoreColor, getMyLiquidityWeight } from '../percentile-utils';
import { useDetailBundle } from './detail-bundle-context';

// Matches services/my_liquidity/metrics.py build_my_liquidity_data() output.
interface MyPremiumDict {
  set_number: string;
  shopee_median_myr_cents: number | null;
  shopee_p25_myr_cents: number | null;
  shopee_p75_myr_cents: number | null;
  shopee_listings_count: number;
  bl_usd_cents: number | null;
  bl_source: string;
  fx_rate_myr_per_usd: number | null;
  premium_median_pct: number | null;
  premium_p25_pct: number | null;
  premium_p75_pct: number | null;
  computed_at: string;
}

interface VelocityDict {
  set_number: string;
  window_days: number;
  total_sold_delta: number | null;
  sold_per_day: number | null;
  snapshots_in_window: number;
  latest_snapshot_at: string | null;
  prior_snapshot_at: string | null;
  latest_total_sold: number | null;
  prior_total_sold: number | null;
}

interface ShopeeLatest {
  listings_count: number;
  unique_sellers: number;
  total_sold_count: number | null;
  min_price_cents: number | null;
  max_price_cents: number | null;
  avg_price_cents: number | null;
  median_price_cents: number | null;
  saturation_score: number;
  saturation_level: string;
  scraped_at: string | null;
}

interface CarousellLatest {
  listings_count: number;
  unique_sellers: number;
  flipped_to_sold_count: number | null;
  min_price_cents: number | null;
  max_price_cents: number | null;
  avg_price_cents: number | null;
  median_price_cents: number | null;
  saturation_score: number;
  saturation_level: string;
  scraped_at: string | null;
}

interface MyLiquidityData {
  set_number: string;
  data_sufficiency: 'full' | 'partial' | 'insufficient';
  premium: MyPremiumDict;
  shopee: {
    velocity_30d: VelocityDict;
    velocity_7d: VelocityDict;
    latest_snapshot: ShopeeLatest | null;
  };
  carousell: {
    latest_snapshot: CarousellLatest | null;
    flipped_to_sold_30d: number | null;
    flipped_to_sold_7d: number | null;
  };
  warnings: string[];
}

interface MyCohortEntry {
  key: string;
  size: number;
  rank: number | null;
  composite_score_pct: number | null;
  my_sold_velocity_30d_pct: number | null;
  my_premium_median_pct_pct: number | null;
  my_saturation_inverse_pct: number | null;
  my_churn_ratio_pct: number | null;
  my_liquidity_ratio_pct: number | null;
}

type MyCohortMap = Record<string, MyCohortEntry>;

const MYR = (cents: number | null) =>
  cents == null ? '--' : `RM ${(cents / 100).toFixed(2)}`;

const USD = (cents: number | null) =>
  cents == null ? '--' : `$${(cents / 100).toFixed(2)}`;

const pct = (value: number | null, digits = 1) =>
  value == null ? '--' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`;

const BL_SOURCE_LABEL: Record<string, string> = {
  bricklink_new: 'BL new sales',
  bricklink_used: 'BL used sales',
  brickeconomy_new: 'BE new value',
  brickeconomy_used: 'BE used value',
  brickeconomy_rrp_usd: 'BE retail RRP (stale)',
  none: 'no benchmark',
};

function PctBadge({
  value,
  weight,
}: {
  value: number | null;
  weight?: number;
}) {
  if (value == null) {
    return (
      <span className="rounded bg-muted/40 px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
        --
      </span>
    );
  }
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-xs font-semibold ${scoreColor(value, weight)} ${scoreBg(value, weight)}`}
    >
      P{Math.round(value)}
    </span>
  );
}

function PremiumSection({ premium }: { premium: MyPremiumDict }) {
  const hasShopee = premium.shopee_listings_count > 0;
  const label = BL_SOURCE_LABEL[premium.bl_source] ?? premium.bl_source;

  return (
    <div className="rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-2">
        <span className="text-xs font-medium">MY Premium vs BrickLink</span>
        <span className="text-muted-foreground text-xs">
          benchmark: {label}
          {premium.bl_usd_cents != null && ` · ${USD(premium.bl_usd_cents)}`}
          {premium.fx_rate_myr_per_usd != null &&
            ` @ ${premium.fx_rate_myr_per_usd.toFixed(2)} MYR/USD`}
        </span>
      </div>
      <div className="grid grid-cols-3 divide-x">
        <div className="px-4 py-3">
          <div className="text-muted-foreground text-xs">P25</div>
          <div className="font-mono text-sm">
            {MYR(premium.shopee_p25_myr_cents)}
          </div>
          <div
            className={`font-mono text-xs ${scoreColor(premium.premium_p25_pct, getMyLiquidityWeight('my_premium_median_pct'))}`}
          >
            {pct(premium.premium_p25_pct, 0)}
          </div>
        </div>
        <div className="px-4 py-3">
          <div className="text-muted-foreground text-xs">Median</div>
          <div className="font-mono text-sm">
            {MYR(premium.shopee_median_myr_cents)}
          </div>
          <div
            className={`font-mono text-xs ${scoreColor(premium.premium_median_pct, getMyLiquidityWeight('my_premium_median_pct'))}`}
          >
            {pct(premium.premium_median_pct, 0)}
          </div>
        </div>
        <div className="px-4 py-3">
          <div className="text-muted-foreground text-xs">P75</div>
          <div className="font-mono text-sm">
            {MYR(premium.shopee_p75_myr_cents)}
          </div>
          <div
            className={`font-mono text-xs ${scoreColor(premium.premium_p75_pct, getMyLiquidityWeight('my_premium_median_pct'))}`}
          >
            {pct(premium.premium_p75_pct, 0)}
          </div>
        </div>
      </div>
      {!hasShopee && (
        <div className="border-t px-4 py-2 text-xs text-muted-foreground">
          No Shopee listings observed yet \u2014 premium unavailable.
        </div>
      )}
    </div>
  );
}

function PlatformCard({
  label,
  listingsCount,
  uniqueSellers,
  saturationScore,
  saturationLevel,
  velocityLabel,
  velocityValue,
  velocityDetail,
  extraRows,
  latestAt,
}: {
  label: string;
  listingsCount: number | null;
  uniqueSellers: number | null;
  saturationScore: number | null;
  saturationLevel: string | null;
  velocityLabel: string;
  velocityValue: string;
  velocityDetail: string;
  extraRows?: Array<{ label: string; value: string }>;
  latestAt: string | null;
}) {
  return (
    <div className="flex-1 rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-2">
        <span className="text-xs font-medium">{label}</span>
        {latestAt && (
          <span className="text-muted-foreground text-xs">
            {new Date(latestAt).toLocaleDateString()}
          </span>
        )}
      </div>
      <div className="divide-y">
        <div className="flex items-center justify-between px-4 py-1.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">Listings</span>
            <span className="text-muted-foreground text-xs">
              {uniqueSellers ?? 0} sellers
            </span>
          </div>
          <span className="font-mono text-xs">
            {listingsCount ?? 0}
          </span>
        </div>
        {saturationScore != null && (
          <div className="flex items-center justify-between px-4 py-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium">Saturation</span>
              <span className="text-muted-foreground text-xs">
                {saturationLevel}
              </span>
            </div>
            <span className="font-mono text-xs">
              {saturationScore.toFixed(1)}
            </span>
          </div>
        )}
        <div className="flex items-center justify-between px-4 py-1.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">{velocityLabel}</span>
            <span className="text-muted-foreground text-xs">
              {velocityDetail}
            </span>
          </div>
          <span className="font-mono text-xs">{velocityValue}</span>
        </div>
        {extraRows?.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between px-4 py-1.5"
          >
            <span className="text-xs font-medium">{row.label}</span>
            <span className="font-mono text-xs">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const MY_COHORT_LABELS: Record<string, { label: string; desc: string }> = {
  half_year: { label: 'Half-Year', desc: 'vs sets released same half' },
  year: { label: 'Year', desc: 'vs sets released same year' },
  theme: { label: 'Theme', desc: 'vs all sets in same theme' },
  year_theme: { label: 'Year + Theme', desc: 'vs same theme & year' },
  price_tier: { label: 'Price Tier', desc: 'vs similarly priced sets' },
  piece_group: { label: 'Piece Group', desc: 'vs similar piece count' },
};

const MY_PCT_FIELDS: {
  key: keyof MyCohortEntry;
  label: string;
  signalKey: string;
}[] = [
  { key: 'composite_score_pct', label: 'Overall', signalKey: '' },
  {
    key: 'my_sold_velocity_30d_pct',
    label: 'Velocity',
    signalKey: 'my_sold_velocity_30d',
  },
  {
    key: 'my_premium_median_pct_pct',
    label: 'Premium',
    signalKey: 'my_premium_median_pct',
  },
  {
    key: 'my_saturation_inverse_pct',
    label: 'Saturation',
    signalKey: 'my_saturation_inverse',
  },
  {
    key: 'my_churn_ratio_pct',
    label: 'Churn',
    signalKey: 'my_churn_ratio',
  },
  {
    key: 'my_liquidity_ratio_pct',
    label: 'Liq.ratio',
    signalKey: 'my_liquidity_ratio',
  },
];

function MyCohortGrid({ cohorts }: { cohorts: MyCohortMap }) {
  const entries = Object.entries(cohorts).filter(
    ([key]) => key in MY_COHORT_LABELS,
  );
  if (entries.length === 0) {
    return (
      <div className="rounded-lg border px-4 py-3 text-xs text-muted-foreground">
        Insufficient MY cohort data \u2014 need \u22653 peers per cohort to rank.
      </div>
    );
  }
  return (
    <div className="rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/50 px-4 py-2">
        <div>
          <span className="text-xs font-medium mr-2">Malaysia Exit</span>
          <span className="text-muted-foreground text-xs">
            percentile vs peer group (higher = better)
          </span>
        </div>
      </div>
      <div className="divide-y">
        {entries.map(([strategy, cohort]) => {
          const meta = MY_COHORT_LABELS[strategy];
          const overall = cohort.composite_score_pct ?? null;
          return (
            <div key={strategy} className="px-4 py-2">
              <div className="mb-1 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{meta.label}</span>
                  <span className="text-muted-foreground text-xs">
                    {meta.desc}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    ({cohort.key})
                  </span>
                </div>
                {overall != null && (
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs font-semibold ${scoreColor(overall)} ${scoreBg(overall)}`}
                  >
                    P{Math.round(overall)}
                    <span className="ml-1 font-normal text-muted-foreground">
                      n={cohort.size}
                    </span>
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2.5">
                {MY_PCT_FIELDS.map(({ key, label, signalKey }) => {
                  const value = cohort[key];
                  const numVal = typeof value === 'number' ? value : null;
                  const w = signalKey
                    ? getMyLiquidityWeight(signalKey)
                    : undefined;
                  return (
                    <span
                      key={key}
                      className="inline-flex items-center gap-1"
                      title={label}
                    >
                      <span className="text-muted-foreground text-xs">
                        {label}
                      </span>
                      <PctBadge value={numVal} weight={w} />
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function MyLiquidityPanel({ setNumber }: { setNumber: string }) {
  const { bundle, loading: bundleLoading } = useDetailBundle();
  const [data, setData] = useState<MyLiquidityData | null | undefined>(
    undefined,
  );
  const [cohorts, setCohorts] = useState<MyCohortMap | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (bundleLoading) return;

    if (bundle?.my_liquidity) {
      setData(bundle.my_liquidity as unknown as MyLiquidityData);
      setLoading(false);
    }
    if (bundle?.my_liquidity_cohorts) {
      setCohorts(bundle.my_liquidity_cohorts as unknown as MyCohortMap);
    }
    if (bundle?.my_liquidity) return;

    const ctrl = new AbortController();
    fetch(`/api/items/${setNumber}/my-liquidity`, { signal: ctrl.signal })
      .then((res) => res.json())
      .then((json) => setData(json.success ? json.data : null))
      .catch((err) => {
        if (err.name !== 'AbortError') setData(null);
      })
      .finally(() => setLoading(false));

    const cohortCtrl = new AbortController();
    fetch(`/api/items/${setNumber}/my-liquidity/cohorts`, {
      signal: cohortCtrl.signal,
    })
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data) setCohorts(json.data);
      })
      .catch(() => {});

    return () => {
      ctrl.abort();
      cohortCtrl.abort();
    };
  }, [setNumber, bundle, bundleLoading]);

  const shopeeVelocityText = useMemo(() => {
    const v30 = data?.shopee.velocity_30d;
    if (!v30) return '--';
    if (v30.total_sold_delta == null) return '--';
    const perDay =
      v30.sold_per_day != null ? `${v30.sold_per_day.toFixed(2)}/day` : '';
    return `${v30.total_sold_delta >= 0 ? '+' : ''}${v30.total_sold_delta} units ${perDay}`.trim();
  }, [data]);

  if (loading) {
    return (
      <div className="rounded-lg border border-border p-4">
        <span className="text-xs font-medium">Malaysia Exit</span>
        <p className="mt-1 text-xs text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!data || data.data_sufficiency === 'insufficient') {
    return (
      <div className="rounded-lg border border-border p-4">
        <span className="text-xs font-medium">Malaysia Exit</span>
        <p className="mt-1 text-xs text-muted-foreground">
          {data?.warnings[0] ??
            'No Shopee or Carousell competition data for this set yet.'}
        </p>
      </div>
    );
  }

  const shopeeLatest = data.shopee.latest_snapshot;
  const carousellLatest = data.carousell.latest_snapshot;

  return (
    <div className="flex flex-col gap-4">
      <PremiumSection premium={data.premium} />

      <div className="flex flex-col gap-4 md:flex-row">
        <PlatformCard
          label="Shopee MY"
          listingsCount={shopeeLatest?.listings_count ?? 0}
          uniqueSellers={shopeeLatest?.unique_sellers ?? 0}
          saturationScore={shopeeLatest?.saturation_score ?? null}
          saturationLevel={shopeeLatest?.saturation_level ?? null}
          velocityLabel="Sold (30d)"
          velocityValue={shopeeVelocityText}
          velocityDetail={
            data.shopee.velocity_7d.total_sold_delta != null
              ? `7d: ${data.shopee.velocity_7d.total_sold_delta >= 0 ? '+' : ''}${data.shopee.velocity_7d.total_sold_delta}`
              : 'need \u22652 snapshots'
          }
          extraRows={
            shopeeLatest?.median_price_cents != null
              ? [
                  {
                    label: 'Median price',
                    value: MYR(shopeeLatest.median_price_cents),
                  },
                ]
              : undefined
          }
          latestAt={shopeeLatest?.scraped_at ?? null}
        />
        <PlatformCard
          label="Carousell MY"
          listingsCount={carousellLatest?.listings_count ?? 0}
          uniqueSellers={carousellLatest?.unique_sellers ?? 0}
          saturationScore={carousellLatest?.saturation_score ?? null}
          saturationLevel={carousellLatest?.saturation_level ?? null}
          velocityLabel="Flipped to sold (30d)"
          velocityValue={
            data.carousell.flipped_to_sold_30d != null
              ? `${data.carousell.flipped_to_sold_30d}`
              : '--'
          }
          velocityDetail={
            data.carousell.flipped_to_sold_7d != null
              ? `7d: ${data.carousell.flipped_to_sold_7d}`
              : 'need \u22652 snapshots'
          }
          extraRows={
            carousellLatest?.median_price_cents != null
              ? [
                  {
                    label: 'Median price',
                    value: MYR(carousellLatest.median_price_cents),
                  },
                ]
              : undefined
          }
          latestAt={carousellLatest?.scraped_at ?? null}
        />
      </div>

      {cohorts && Object.keys(cohorts).length > 0 ? (
        <MyCohortGrid cohorts={cohorts} />
      ) : (
        <div className="rounded-lg border px-4 py-3 text-xs text-muted-foreground">
          Insufficient MY cohort data \u2014 need \u22653 peers per cohort.
        </div>
      )}

      {data.warnings.length > 0 && (
        <div className="rounded-lg border border-yellow-500/40 bg-yellow-500/5 px-4 py-2">
          <ul className="list-disc pl-4 text-xs text-muted-foreground">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
