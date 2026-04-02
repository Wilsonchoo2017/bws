import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/items/{setNumber}/minifigures/scrape', {
  errorMessage: 'Failed to scrape minifigures',
});
