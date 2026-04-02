import { proxyGet, proxyDelete } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/transactions/{txnId}', {
  errorMessage: 'Transaction not found',
});

export const DELETE = proxyDelete('/api/portfolio/transactions/{txnId}', {
  errorMessage: 'Failed to delete transaction',
});
