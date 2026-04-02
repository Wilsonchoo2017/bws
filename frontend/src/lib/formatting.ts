export function formatPrice(
  cents: number | null,
  currency?: string | null
): string {
  if (cents === null) return '-';
  const amount = (cents / 100).toFixed(2);
  if (currency === 'USD') return `$${amount}`;
  return `RM${amount}`;
}
