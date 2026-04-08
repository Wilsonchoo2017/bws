import { proxyGet, proxyDelete, proxyPut } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/transactions/{txnId}', {
  errorMessage: 'Transaction not found',
});

export const PUT = proxyPut('/api/portfolio/transactions/{txnId}', {
  errorMessage: 'Failed to update transaction',
});

export const DELETE = proxyDelete('/api/portfolio/transactions/{txnId}', {
  errorMessage: 'Failed to delete transaction',
});
