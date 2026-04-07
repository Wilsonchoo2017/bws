import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/settings/reset', {
  errorMessage: 'Failed to reset settings',
});
