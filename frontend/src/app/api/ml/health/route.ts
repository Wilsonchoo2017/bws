import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/ml/health', {
  errorMessage: 'Failed to check ML health',
});
