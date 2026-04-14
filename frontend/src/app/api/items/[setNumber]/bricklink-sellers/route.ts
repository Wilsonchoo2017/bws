import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/bricklink-sellers', {
  errorMessage: 'Failed to fetch BrickLink sellers',
});
