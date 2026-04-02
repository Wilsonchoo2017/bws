import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/enrichment/enrich-missing', {
  errorMessage: 'Failed to enrich missing',
  forwardBody: 'optional',
  wrapSuccess: true,
});
