import type { ItemDetail, MinifigurePrice } from '../types';

export interface ParsedDimensions {
  length: string;
  width: string;
  height: string;
}

/**
 * Parse BrickLink-style dimensions string "26.2 x 14 x 7.2 cm" into L/W/H.
 */
export function parseDimensions(dim: string | null): ParsedDimensions | null {
  if (!dim) return null;
  const match = dim.match(
    /(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)/
  );
  if (!match) return null;
  return { length: match[1], width: match[2], height: match[3] };
}

/**
 * Parse weight string like "1.25 Kg" or "1250g" into a kg string.
 */
export function parseWeight(weight: string | null): string | null {
  if (!weight) return null;
  const trimmed = weight.trim().toLowerCase();

  // "1.25 kg" or "1.25kg"
  const kgMatch = trimmed.match(/^(\d+(?:\.\d+)?)\s*kg$/);
  if (kgMatch) return kgMatch[1];

  // "1250g" or "1250 g"
  const gMatch = trimmed.match(/^(\d+(?:\.\d+)?)\s*g$/);
  if (gMatch) return (parseFloat(gMatch[1]) / 1000).toFixed(2);

  return null;
}

/**
 * Shipping-adjusted dimensions: adds 5cm to each side for the shipping box.
 */
export function shippingDimensions(dim: string | null): ParsedDimensions | null {
  const parsed = parseDimensions(dim);
  if (!parsed) return null;
  return {
    length: (parseFloat(parsed.length) + 5).toFixed(1),
    width: (parseFloat(parsed.width) + 5).toFixed(1),
    height: (parseFloat(parsed.height) + 5).toFixed(1),
  };
}

/**
 * Shipping-adjusted weight: adds 20% buffer for packaging materials.
 */
export function shippingWeight(weight: string | null): string | null {
  const kg = parseWeight(weight);
  if (!kg) return null;
  return (parseFloat(kg) * 1.2).toFixed(2);
}

/**
 * Generate a marketplace-optimized listing title.
 */
export function generateListingTitle(item: ItemDetail): string {
  const parts: string[] = ['LEGO'];

  if (item.theme) parts.push(item.theme);
  parts.push(item.set_number);
  if (item.title) parts.push(item.title);

  const extras: string[] = [];
  if (item.parts_count) extras.push(`${item.parts_count}pcs`);
  if (item.minifig_count) extras.push(`${item.minifig_count} Minifigures`);
  if (extras.length > 0) parts.push(`(${extras.join(', ')})`);

  parts.push('MISB NEW SEALED');

  if (item.year_retired) parts.push('RETIRED');

  return parts.join(' ');
}

/**
 * Generate a marketplace listing description.
 */
export function generateListingDescription(
  item: ItemDetail,
  minifigures: MinifigurePrice[]
): string {
  const lines: string[] = [];

  // Keywords up top
  lines.push('100% Genuine LEGO Product');
  lines.push('Brand New | Factory Sealed | MISB');
  lines.push('Ready Stock');
  lines.push('Not for fussy buyers or box collectors.');
  lines.push('');

  // Specs
  if (item.theme) lines.push(`Theme: ${item.theme}`);
  if (item.parts_count)
    lines.push(`Pieces: ${item.parts_count.toLocaleString()}`);

  // Minifigures
  if (item.minifig_count && minifigures.length > 0) {
    const names = minifigures
      .filter((mf) => mf.name)
      .map((mf) => mf.name)
      .join(', ');
    lines.push(`Minifigures: ${item.minifig_count} (${names})`);
  } else if (item.minifig_count) {
    lines.push(`Minifigures: ${item.minifig_count}`);
  }

  return lines.join('\n');
}
