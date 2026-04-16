import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/operations/tasks', {
  errorMessage: 'Failed to load background tasks',
});
