import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/portfolio/transactions/bill', {
  errorMessage: 'Failed to create bill transactions',
  forwardBody: true,
});
