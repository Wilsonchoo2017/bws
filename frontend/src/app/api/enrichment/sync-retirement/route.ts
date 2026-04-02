import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/enrichment/sync-retirement', {
  errorMessage: 'Failed to sync retirement',
  forwardBody: 'optional',
  wrapSuccess: true,
});
