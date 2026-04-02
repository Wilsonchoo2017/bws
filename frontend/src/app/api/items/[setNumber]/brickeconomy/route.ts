import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/brickeconomy', {
  errorMessage: 'Failed to fetch BrickEconomy data',
});
