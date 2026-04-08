import { proxyGet, proxyPost } from '@/lib/api-proxy';

export const GET = proxyGet('/api/cart', {
  errorMessage: 'Failed to fetch cart',
});

export const POST = proxyPost('/api/cart', {
  errorMessage: 'Failed to add to cart',
  forwardBody: true,
});
