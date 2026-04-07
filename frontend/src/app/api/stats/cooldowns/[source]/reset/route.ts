import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/stats/cooldowns/{source}/reset', {
  errorMessage: 'Failed to reset cooldown',
});
