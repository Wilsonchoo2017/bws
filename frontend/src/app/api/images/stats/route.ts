import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/images/stats', {
  errorMessage: 'Failed to connect to API',
  wrapSuccess: true,
});
