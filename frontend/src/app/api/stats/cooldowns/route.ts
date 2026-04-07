import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/stats/cooldowns', {
  errorMessage: 'Failed to fetch cooldown status',
});
