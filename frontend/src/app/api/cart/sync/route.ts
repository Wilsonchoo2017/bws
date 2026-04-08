import { proxyPut } from '@/lib/api-proxy';

export const PUT = proxyPut('/api/cart/sync', {
  errorMessage: 'Failed to sync cart',
});
