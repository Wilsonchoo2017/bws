import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/minifigures', {
  errorMessage: 'Failed to fetch minifigures',
});
