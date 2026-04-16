import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/ml/growth/reload', {
  errorMessage: 'Failed to reload growth models',
});

export const maxDuration = 600;
