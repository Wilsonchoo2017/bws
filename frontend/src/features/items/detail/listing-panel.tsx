'use client';

import { useEffect, useRef, useState } from 'react';
import { CopyButton } from '@/components/ui/copy-button';
import { formatPrice } from '@/lib/formatting';
import type { ItemDetail, KeepaData, MinifigurePrice } from '../types';
import { getLatestPriceBySource } from '../types';
import {
  generateListingDescription,
  generateListingTitle,
  shippingDimensions,
  shippingWeight,
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
  const dims = shippingDimensions(item.dimensions);
  return [
    { label: 'Title', value: generateListingTitle(item) },
    {
      label: 'Description',
      value: generateListingDescription(item, minifigures),
      multiline: true,
    },
    { label: 'Shipping Weight (kg)', value: shippingWeight(item.weight) },
    { label: 'Shipping Length (cm)', value: dims?.length ?? null },
    { label: 'Shipping Width (cm)', value: dims?.width ?? null },
    { label: 'Shipping Height (cm)', value: dims?.height ?? null },
    { label: 'Brand', value: 'LEGO' },
    { label: 'Condition', value: 'New' },
  ];
}

function FieldRow({ label, value, multiline }: ListingField) {
  if (!value) return null;

  return (
    <div className='flex items-start gap-3 border-b border-border py-3 last:border-0'>
      <div className='w-28 shrink-0 text-xs font-medium text-muted-foreground uppercase'>
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
      <div className='w-28 shrink-0 text-xs font-medium text-muted-foreground uppercase'>
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

function getBricklinkNewCents(item: ItemDetail): number | null {
  const latest = getLatestPriceBySource(item.prices);
  const blNew = latest.get('bricklink_new');
  return blNew?.price_cents ?? null;
}

interface ListingPanelProps {
  item: ItemDetail;
}

export function ListingPanel({ item }: ListingPanelProps) {
  const [collapsed, setCollapsed] = useState(true);
  const [minifigures, setMinifigures] = useState<MinifigurePrice[]>([]);
  const [keepaTitle, setKeepaTitle] = useState<string | null>(null);
  const [maxPhotos, setMaxPhotos] = useState(9);
  const [shopeeCategory, setShopeeCategory] = useState('');
  const [listingPrice, setListingPrice] = useState(
    item.listing_price_cents ? (item.listing_price_cents / 100).toFixed(2) : ''
  );
  const [priceSaved, setPriceSaved] = useState(false);
  const hasFetched = useRef(false);

  useEffect(() => {
    if (collapsed || hasFetched.current) return;
    hasFetched.current = true;

    // Fetch minifigures
    fetch(`/api/items/${item.set_number}/minifigures`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data?.minifigures) {
          setMinifigures(json.data.minifigures);
        }
      })
      .catch(() => {});

    // Fetch Keepa Amazon title
    fetch(`/api/items/${item.set_number}/keepa`)
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data) {
          const keepa = json.data as KeepaData;
          if (keepa.title) setKeepaTitle(keepa.title);
        }
      })
      .catch(() => {});

    // Fetch listing settings
    fetch('/api/settings')
      .then((res) => res.json())
      .then((json) => {
        if (json.success && json.data?.listing?.shopee) {
          setMaxPhotos(json.data.listing.shopee.max_photos ?? 9);
          setShopeeCategory(json.data.listing.shopee.category ?? '');
        }
      })
      .catch(() => {});
  }, [item.set_number, collapsed]);

  const saveListingPrice = () => {
    const cents = listingPrice ? Math.round(parseFloat(listingPrice) * 100) : null;
    if (listingPrice && Number.isNaN(parseFloat(listingPrice))) return;
    fetch(`/api/items/${item.set_number}/listing-price`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ price_cents: cents }),
    })
      .then((res) => res.json())
      .then((json) => {
        if (json.success) {
          setPriceSaved(true);
          setTimeout(() => setPriceSaved(false), 2000);
        }
      })
      .catch(() => {});
  };

  // Check if listing price is 10%+ below BrickLink New
  const blNewCents = getBricklinkNewCents(item);
  const listingCents = listingPrice ? Math.round(parseFloat(listingPrice) * 100) : null;
  const priceWarning =
    blNewCents && listingCents && listingCents < blNewCents * 0.9
      ? `Listing price is ${Math.round((1 - listingCents / blNewCents) * 100)}% below BrickLink New (${formatPrice(blNewCents, 'USD')})`
      : null;

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

  // All available images: set image + minifig images, capped at maxPhotos
  const allImages: { key: string; url: string; alt: string }[] = [];
  if (item.image_url) {
    allImages.push({ key: 'set', url: item.image_url, alt: 'Set' });
  }
  for (const mf of minifigImages) {
    allImages.push({ key: mf.id, url: mf.url, alt: mf.name ?? mf.id });
  }
  const displayImages = allImages.slice(0, maxPhotos);

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
        {/* Listing Price */}
        <div className='flex items-center gap-3 border-b border-border py-3'>
          <div className='w-28 shrink-0 text-xs font-medium text-muted-foreground uppercase'>
            Listing Price
          </div>
          <div className='flex items-center gap-2'>
            <span className='text-sm text-muted-foreground'>RM</span>
            <input
              type='number'
              step='0.01'
              min='0'
              value={listingPrice}
              onChange={(e) => setListingPrice(e.target.value)}
              onBlur={saveListingPrice}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveListingPrice();
              }}
              placeholder='0.00'
              className='border-border bg-background h-8 w-28 rounded border px-2 text-right font-mono text-sm'
            />
            {priceSaved && (
              <span className='text-xs text-green-600 dark:text-green-400'>
                Saved
              </span>
            )}
          </div>
        </div>

        {/* Price warning */}
        {priceWarning && (
          <div className='border-b border-border py-2'>
            <span className='text-xs text-amber-600 dark:text-amber-400'>
              {priceWarning}
            </span>
          </div>
        )}

        {/* Amazon Title (Keepa) */}
        {keepaTitle && (
          <div className='flex items-start gap-3 border-b border-border py-3'>
            <div className='w-28 shrink-0 text-xs font-medium text-muted-foreground uppercase'>
              Amazon Title
            </div>
            <span className='min-w-0 flex-1 text-sm text-muted-foreground'>
              {keepaTitle}
            </span>
            <CopyButton value={keepaTitle} label='Amazon Title' />
          </div>
        )}

        {/* Title + Description */}
        <FieldRow {...fields[0]} />
        <FieldRow {...fields[1]} />

        <PriceRefRow prices={buildRefPrices(item)} />

        {/* Category */}
        {shopeeCategory && (
          <FieldRow label='Category' value={shopeeCategory} />
        )}

        {/* Remaining fields (shipping weight, dims, brand, condition) */}
        {fields.slice(2).map((f) => (
          <FieldRow key={f.label} {...f} />
        ))}
      </div>

      {/* Images */}
      <div className='border-t border-border px-4 py-3'>
        <div className='mb-2 flex items-center justify-between'>
          <span className='text-xs font-medium text-muted-foreground uppercase'>
            Images ({displayImages.length}/{maxPhotos})
          </span>
          <CopyButton value='~/.bws/images/sets' label='Images path' />
        </div>
        <div className='flex flex-wrap gap-2'>
          {displayImages.map((img) => (
            <img
              key={img.key}
              src={img.url}
              alt={img.alt}
              title={img.alt}
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
