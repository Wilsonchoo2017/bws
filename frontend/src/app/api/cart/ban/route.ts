import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/cart/ban', {
  errorMessage: 'Failed to fetch banned items',
});
