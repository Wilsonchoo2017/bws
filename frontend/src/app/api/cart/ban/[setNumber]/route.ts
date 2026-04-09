import { proxyPost, proxyDelete } from '@/lib/api-proxy';

export const POST = proxyPost('/api/cart/ban/{setNumber}', {
  errorMessage: 'Failed to ban from cart',
});

export const DELETE = proxyDelete('/api/cart/ban/{setNumber}', {
  errorMessage: 'Failed to unban from cart',
});
