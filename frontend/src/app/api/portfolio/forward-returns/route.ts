import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/forward-returns', {
  errorMessage: 'Failed to fetch forward returns',
});
