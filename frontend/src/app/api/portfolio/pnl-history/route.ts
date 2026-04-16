import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/pnl-history', {
  errorMessage: 'Failed to fetch PnL history',
});
