import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/summary', {
  errorMessage: 'Failed to fetch summary',
});
