import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/liquidity/bulk', {
  errorMessage: 'Failed to fetch liquidity data',
});
