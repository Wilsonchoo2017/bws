import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/stats/coverage', {
  errorMessage: 'Failed to fetch coverage stats',
});
