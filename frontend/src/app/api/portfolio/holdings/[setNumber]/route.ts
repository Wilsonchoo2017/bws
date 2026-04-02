import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/portfolio/holdings/{setNumber}', {
  errorMessage: 'Holding not found',
});
