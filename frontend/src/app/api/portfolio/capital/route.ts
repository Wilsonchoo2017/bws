import { proxyGet, proxyPut } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/capital', {
  errorMessage: 'Failed to fetch capital',
});

export const PUT = proxyPut('/api/portfolio/capital', {
  errorMessage: 'Failed to update capital',
});
