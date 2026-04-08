import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/liquidity/cohorts/bulk', {
  errorMessage: 'Failed to fetch liquidity cohort data',
});
