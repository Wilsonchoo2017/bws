import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/ml/growth/predict/{setNumber}', {
  errorMessage: 'Failed to run ML prediction',
});
