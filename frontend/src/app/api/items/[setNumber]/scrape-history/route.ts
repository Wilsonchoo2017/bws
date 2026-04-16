import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/scrape-history', {
  errorMessage: 'Failed to fetch scrape history',
});
