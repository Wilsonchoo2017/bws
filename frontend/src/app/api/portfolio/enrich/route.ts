import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/portfolio/enrich', {
  errorMessage: 'Failed to enrich portfolio',
});
