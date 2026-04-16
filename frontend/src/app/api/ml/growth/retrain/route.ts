import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/ml/growth/retrain', {
  errorMessage: 'Failed to retrain growth models',
});

export const maxDuration = 600;
