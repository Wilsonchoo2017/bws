import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/ml/growth/predictions/{setNumber}', {
  errorMessage: 'Failed to fetch growth prediction',
});
