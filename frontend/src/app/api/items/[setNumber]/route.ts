import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items/{setNumber}', {
  errorMessage: 'Item not found',
});
