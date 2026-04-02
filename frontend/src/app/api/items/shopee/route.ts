import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/shopee', {
  errorMessage: 'Failed to fetch shopee items',
});
