import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/scrape/jobs/{jobId}', {
  errorMessage: 'Job not found',
});
