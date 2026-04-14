import { proxyPost } from '@/lib/api-proxy';

export const POST = proxyPost(
  '/api/scrape/shopee/captcha-events/{eventId}/verify',
  { errorMessage: 'Failed to start verification' }
);
