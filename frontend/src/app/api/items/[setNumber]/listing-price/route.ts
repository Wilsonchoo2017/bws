import { proxyPut } from '@/lib/api-proxy';

export const PUT = proxyPut('/api/items/{setNumber}/listing-price', {
  errorMessage: 'Failed to update listing price',
});
