import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/scrape/scrapers', {
  errorMessage: 'Failed to fetch scrapers',
});
