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
 * Generate a marketplace-optimized listing title.
 */
export function generateListingTitle(item: ItemDetail): string {
  const parts: string[] = ['LEGO'];

  if (item.theme) parts.push(item.theme);
  parts.push(item.set_number);
  if (item.title) parts.push(item.title);

  const extras: string[] = [];
  if (item.parts_count) extras.push(`${item.parts_count} pcs`);
  if (item.minifig_count) extras.push(`${item.minifig_count} Minifigures`);
  if (extras.length > 0) parts.push(`(${extras.join(', ')})`);

  parts.push('NEW SEALED');

  return parts.join(' ');
}

/**
 * Generate a bullet-point listing description.
 */
export function generateListingDescription(
  item: ItemDetail,
  minifigures: MinifigurePrice[]
): string {
  const lines: string[] = [];

  // Header
  const header = item.theme
    ? `LEGO ${item.theme} - ${item.title ?? item.set_number} (${item.set_number})`
    : `LEGO ${item.title ?? item.set_number} (${item.set_number})`;
  lines.push(header);
  lines.push('');

  // Specs
  lines.push(`Set Number: ${item.set_number}`);
  if (item.theme) lines.push(`Theme: ${item.theme}`);
  if (item.year_released) lines.push(`Year Released: ${item.year_released}`);
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

  if (item.dimensions) lines.push(`Box Dimensions: ${item.dimensions}`);

  const weight = parseWeight(item.weight);
  if (weight) lines.push(`Weight: ${weight} kg`);

  lines.push(`Condition: Brand New, Factory Sealed`);
  lines.push('');
  lines.push('100% genuine LEGO product.');

  return lines.join('\n');
}
