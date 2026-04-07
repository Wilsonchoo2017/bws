import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/settings', {
  errorMessage: 'Failed to fetch settings',
});
