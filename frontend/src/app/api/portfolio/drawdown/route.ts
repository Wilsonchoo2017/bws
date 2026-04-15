import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/drawdown', {
  errorMessage: 'Failed to fetch drawdown',
});
