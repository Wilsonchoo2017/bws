'use client';

import { ExternalLinkIcon } from 'lucide-react';
import { formatPrice } from '@/lib/formatting';
import { useDetailBundle } from './detail-bundle-context';

interface ShopSummary {
  country_code: string | null;
  country_name: string | null;
  store_id: string | null;
  store_name: string | null;
  price_cents: number;
  currency: string | null;
  quantity: number | null;
}

interface AsiaStats {
  count: number;
  min_cents: number;
  max_cents: number;
  mean_cents: number;
  median_cents: number;
  currency: string | null;
  lowest_shop: ShopSummary;
}

interface ConditionGrouping {
  global_count: number;
  global_lowest: ShopSummary;
  asia: AsiaStats | null;
}

interface BricklinkSellersData {
  item_id: string;
  scraped_at: string | null;
  new: ConditionGrouping | null;
  used: ConditionGrouping | null;
}

function storeUrl(storeId: string | null): string | null {
  if (!storeId) return null;
  return `https://www.bricklink.com/store.asp?p=${encodeURIComponent(storeId)}`;
}

function ShopBadge({ shop, label }: { shop: ShopSummary; label: string }) {
  const href = storeUrl(shop.store_id);
  const country = shop.country_code ?? '??';
  const name = shop.store_name ?? 'Unknown shop';
  return (
    <div className='rounded-md border bg-white px-3 py-2 text-xs dark:bg-zinc-900'>
      <div className='text-[10px] font-medium uppercase tracking-wide text-muted-foreground'>
        {label}
      </div>
      <div className='mt-1 flex items-baseline gap-2'>
        <span className='text-base font-semibold'>
          {formatPrice(shop.price_cents, shop.currency)}
        </span>
        <span className='rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300'>
          {country}
        </span>
      </div>
      <div className='mt-1 text-muted-foreground'>
        {href ? (
          <a
            href={href}
            target='_blank'
            rel='noopener noreferrer'
            className='inline-flex items-center gap-1 hover:text-foreground'
          >
            {name}
            <ExternalLinkIcon className='h-3 w-3' />
          </a>
        ) : (
          name
        )}
        {shop.quantity != null && shop.quantity > 0 && (
          <span className='ml-1'>· qty {shop.quantity}</span>
        )}
      </div>
    </div>
  );
}

function StatCell({
  label,
  cents,
  currency,
}: {
  label: string;
  cents: number | null;
  currency: string | null;
}) {
  return (
    <div className='rounded-md border bg-white px-3 py-2 dark:bg-zinc-900'>
      <div className='text-[10px] font-medium uppercase tracking-wide text-muted-foreground'>
        {label}
      </div>
      <div className='mt-1 text-sm font-semibold'>
        {formatPrice(cents, currency)}
      </div>
    </div>
  );
}

function ConditionGroup({
  title,
  group,
}: {
  title: string;
  group: ConditionGrouping | null;
}) {
  if (!group) {
    return (
      <div className='rounded-lg border bg-zinc-50/50 p-4 dark:bg-zinc-900/40'>
        <h3 className='mb-2 text-sm font-semibold'>{title}</h3>
        <p className='text-xs text-muted-foreground'>No listings found.</p>
      </div>
    );
  }

  const asia = group.asia;

  return (
    <div className='rounded-lg border bg-zinc-50/50 p-4 dark:bg-zinc-900/40'>
      <div className='mb-3 flex items-baseline justify-between'>
        <h3 className='text-sm font-semibold'>{title}</h3>
        <span className='text-xs text-muted-foreground'>
          {asia ? `${asia.count} Asia` : '0 Asia'} · {group.global_count} global
        </span>
      </div>

      <div className='mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2'>
        {asia && <ShopBadge shop={asia.lowest_shop} label='Lowest in Asia' />}
        <ShopBadge shop={group.global_lowest} label='Lowest globally' />
      </div>

      {asia ? (
        <>
          <div className='mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground'>
            Asia stats
          </div>
          <div className='grid grid-cols-2 gap-2 sm:grid-cols-4'>
            <StatCell label='Min' cents={asia.min_cents} currency={asia.currency} />
            <StatCell label='Median' cents={asia.median_cents} currency={asia.currency} />
            <StatCell label='Mean' cents={asia.mean_cents} currency={asia.currency} />
            <StatCell label='Max' cents={asia.max_cents} currency={asia.currency} />
          </div>
        </>
      ) : (
        <p className='text-xs text-muted-foreground'>
          No Asian sellers in latest snapshot.
        </p>
      )}
    </div>
  );
}

export function BricklinkSellersPanel({ setNumber: _setNumber }: { setNumber: string }) {
  const { bundle, loading } = useDetailBundle();
  const data = bundle?.bricklink_sellers as BricklinkSellersData | null | undefined;

  if (loading && !data) {
    return (
      <div>
        <h2 className='mb-3 text-lg font-semibold'>BrickLink Sellers</h2>
        <p className='text-sm text-muted-foreground'>Loading sellers…</p>
      </div>
    );
  }

  if (!data || (!data.new && !data.used)) {
    return (
      <div>
        <h2 className='mb-3 text-lg font-semibold'>BrickLink Sellers</h2>
        <p className='text-sm text-muted-foreground'>
          No store-listing snapshot available yet.
        </p>
      </div>
    );
  }

  const snapshotDate = data.scraped_at
    ? new Date(data.scraped_at).toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null;

  return (
    <div>
      <div className='mb-3 flex items-baseline justify-between'>
        <h2 className='text-lg font-semibold'>BrickLink Sellers</h2>
        {snapshotDate && (
          <span className='text-xs text-muted-foreground'>
            Snapshot: {snapshotDate}
          </span>
        )}
      </div>
      <div className='grid grid-cols-1 gap-3 lg:grid-cols-2'>
        <ConditionGroup title='New listings' group={data.new} />
        <ConditionGroup title='Used listings' group={data.used} />
      </div>
    </div>
  );
}
