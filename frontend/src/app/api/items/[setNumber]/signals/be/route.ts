import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/signals/be', {
  errorMessage: 'Failed to fetch BrickEconomy signals',
});
