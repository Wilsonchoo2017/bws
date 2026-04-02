import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/keepa', {
  errorMessage: 'Failed to fetch Keepa data',
});
