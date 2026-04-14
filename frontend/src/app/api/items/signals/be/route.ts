import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/signals/be', {
  errorMessage: 'Failed to fetch BE signals',
});
