import { proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet(
  '/api/scrape/shopee/captcha-events/{eventId}',
  { errorMessage: 'Captcha event not found' }
);
