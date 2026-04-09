import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}/detail-bundle', {
  errorMessage: 'Failed to fetch item detail bundle',
});
