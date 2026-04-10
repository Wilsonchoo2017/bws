import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/reallocation', {
  errorMessage: 'Failed to fetch reallocation analysis',
});
