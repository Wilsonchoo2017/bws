import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/enrichment/enrich-missing-dimensions', {
  errorMessage: 'Failed to enrich missing dimensions',
  forwardBody: 'optional',
  wrapSuccess: true,
});
