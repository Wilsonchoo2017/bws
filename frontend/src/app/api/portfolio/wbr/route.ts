import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/wbr', {
  errorMessage: 'Failed to fetch WBR metrics',
});
