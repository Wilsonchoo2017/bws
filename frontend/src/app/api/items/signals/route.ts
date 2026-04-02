import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/signals', {
  errorMessage: 'Failed to fetch signals',
});
