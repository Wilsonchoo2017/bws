import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/settings/reset/{section}', {
  errorMessage: 'Failed to reset settings section',
});
