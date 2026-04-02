import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/holdings', {
  errorMessage: 'Failed to fetch holdings',
});
