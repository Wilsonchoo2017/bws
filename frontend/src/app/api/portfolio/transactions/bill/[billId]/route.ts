import { proxyPut } from '@/lib/api-proxy';

export const PUT = proxyPut('/api/portfolio/transactions/bill/{billId}', {
  errorMessage: 'Failed to update bill',
});
