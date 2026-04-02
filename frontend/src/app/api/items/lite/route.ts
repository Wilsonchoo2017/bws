import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/lite', {
  errorMessage: 'Failed to fetch items',
});
