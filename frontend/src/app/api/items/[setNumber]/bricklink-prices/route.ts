import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/bricklink-prices', {
  errorMessage: 'Failed to fetch BrickLink prices',
});
