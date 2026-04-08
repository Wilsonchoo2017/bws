import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/listing/login', {
  errorMessage: 'Failed to open Shopee Seller Center',
  forwardBody: true,
});
