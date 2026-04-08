import { proxyDelete } from '@/lib/api-proxy';

export const DELETE = proxyDelete('/api/cart/{setNumber}', {
  errorMessage: 'Failed to remove from cart',
});
