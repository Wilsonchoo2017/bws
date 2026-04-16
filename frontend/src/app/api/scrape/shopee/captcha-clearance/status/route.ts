import { proxyGet } from '@/lib/api-proxy';

export const dynamic = 'force-dynamic';

export const GET = proxyGet('/api/scrape/shopee/captcha-clearance/status');
