import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/enrichment/scrape-missing-minifigs', {
  errorMessage: 'Failed to scrape missing minifigs',
  forwardBody: 'optional',
  wrapSuccess: true,
});
