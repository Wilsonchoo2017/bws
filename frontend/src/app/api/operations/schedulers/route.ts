import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/operations/schedulers', {
  errorMessage: 'Failed to load schedulers',
});
