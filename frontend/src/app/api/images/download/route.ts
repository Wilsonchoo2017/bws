import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost('/api/images/download', {
  errorMessage: 'Failed to connect to API',
  wrapSuccess: true,
});
