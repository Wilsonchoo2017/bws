import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/competition', {
  errorMessage: 'Failed to fetch competition data',
});
