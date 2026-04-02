'use client';

import { useEffect, useRef, useState } from 'react';
import { CopyButton } from '@/components/ui/copy-button';
import type { ItemDetail, MinifigurePrice } from '../types';
import { formatPrice, getLatestPriceBySource } from '../types';
import {
  generateListingDescription,
  generateListingTitle,
  parseDimensions,
  parseWeight,
} from './listing-template';

interface ListingField {
  label: string;
  value: string | null;
  multiline?: boolean;
}

function buildListingFields(
  item: ItemDetail,
  minifigures: MinifigurePrice[]
): ListingField[] {
  const dims = parseDimensions(item.dimensions);
  return [
    { label: 'Title', value: generateListingTitle(item) },
    {
      label: 'Description',
      value: generateListingDescription(item, minifigures),
      multiline: true,
    },
    { label: 'Weight (kg)', value: parseWeight(item.weight) },
    { label: 'Length (cm)', value: dims?.length ?? null },
    { label: 'Width (cm)', value: dims?.width ?? null },
    { label: 'Height (cm)', value: dims?.height ?? null },
    { label: 'Brand', value: 'LEGO' },
    { label: 'Condition', value: 'New' },
  ];
}

function FieldRow({ label, value, multiline }: ListingField) {
  if (!value) return null;

  return (
    <div className='flex items-start gap-3 border-b border-border py-3 last:border-0'>
      <div className='w-24 shrink-0 text-xs font-medium text-muted-foreground uppercase'>
        {label}
      </div>
      <div className='min-w-0 flex-1'>
        {multiline ? (
          <pre className='whitespace-pre-wrap text-sm font-sans'>{value}</pre>
        ) : (
          <span className='text-sm'>{value}</span>
        )}
      </div>
      <CopyButton value={value} label={label} />
    </div>
  );
}

interface PriceRefRowProps {
  prices: { label: string; display: string }[];
}

function PriceRefRow({ prices }: PriceRefRowProps) {
  if (prices.length === 0) return null;

  return (
    <div className='flex items-start gap-3 border-b border-border py-3'>
      <div className='w-24 shrink-0 text-xs font-medium text-muted-foreground uppercase'>
        Price Ref
      </div>
      <div className='flex flex-wrap gap-3 text-sm'>
        {prices.map((p) => (
          <span key={p.label} className='text-muted-foreground'>
            {p.label}: {p.display}
          </span>
        ))}
      </div>
    </div>
  );
}

function buildRefPrices(item: ItemDetail): { label: string; display: string }[] {
  const latest = getLatestPriceBySource(item.prices);
  const refs: { label: string; display: string }[] = [];

  const blNew = latest.get('bricklink_new');
  if (blNew) refs.push({ label: 'BrickLink New', display: formatPrice(blNew.price_cents, 'USD') });

  const shopee = latest.get('shopee');
  if (shopee) refs.push({ label: 'Shopee', display: formatPrice(shopee.price_cents, 'MYR') });

  return refs;
}

interface ListingPanelProps {
  item: ItemDetail;
}

export function ListingPanel({ item }: ListingPanelProps) {
  const [collapsed, setCollapsed] = useState(true);
  const [minifigures, setMinifigures] = useState<MinifigurePrice[]>([]);
  const hasFetchedMinifigs = useRef(false);

  useEffect(() => {
    if (collapsed || hasFetchedMinifigs.current) return;
    hasFetchedMinifigs.current = true;
    fetch(`/api/items/${item.set_number}/minifigures`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data?.minifigures) {
          setMinifigures(json.data.minifigures);
        }
      })
      .catch((err) => {
        console.error('Failed to fetch minifigures for listing:', err);
      });
  }, [item.set_number, collapsed]);

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className='w-full rounded-lg border border-dashed border-border px-4 py-3 text-left text-sm font-medium text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground'
      >
        Generate Listing
      </button>
    );
  }

  const fields = buildListingFields(item, minifigures);
  const titleField = fields[0];
  const descField = fields[1];
  const copyAllValue =
    titleField?.value && descField?.value
      ? `${titleField.value}\n\n${descField.value}`
      : '';

  const minifigImages = minifigures
    .filter((mf) => mf.image_url)
    .map((mf) => ({ id: mf.minifig_id, url: mf.image_url!, name: mf.name }));

  return (
    <div className='rounded-lg border border-border'>
      <div className='flex items-center justify-between border-b border-border px-4 py-3'>
        <h2 className='text-sm font-semibold'>Listing Helper</h2>
        <button
          onClick={() => setCollapsed(true)}
          className='text-xs text-muted-foreground hover:text-foreground'
        >
          Collapse
        </button>
      </div>

      <div className='px-4'>
        {/* Title + Description */}
        <FieldRow {...fields[0]} />
        <FieldRow {...fields[1]} />

        <PriceRefRow prices={buildRefPrices(item)} />

        {/* Remaining fields (weight, dims, brand, condition) */}
        {fields.slice(2).map((f) => (
          <FieldRow key={f.label} {...f} />
        ))}
      </div>

      {/* Images */}
      <div className='border-t border-border px-4 py-3'>
        <div className='mb-2 flex items-center justify-between'>
          <span className='text-xs font-medium text-muted-foreground uppercase'>
            Images
          </span>
          <CopyButton value='~/.bws/images/sets' label='Images path' />
        </div>
        <div className='flex flex-wrap gap-2'>
          {item.image_url && (
            <img
              src={item.image_url}
              alt='Set'
              className='h-20 w-20 rounded border border-border object-cover'
            />
          )}
          {minifigImages.map((mf) => (
            <img
              key={mf.id}
              src={mf.url}
              alt={mf.name ?? mf.id}
              title={mf.name ?? mf.id}
              className='h-20 w-20 rounded border border-border object-cover'
            />
          ))}
        </div>
      </div>

      {/* Copy All */}
      {copyAllValue && (
        <div className='border-t border-border px-4 py-3'>
          <CopyButton value={copyAllValue} label='Title + Description' />
        </div>
      )}
    </div>
  );
}
