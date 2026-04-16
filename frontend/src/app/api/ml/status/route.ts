import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/ml/status', {
  errorMessage: 'Failed to fetch ML status',
});
