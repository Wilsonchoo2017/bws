import { proxyPut } from '@/lib/api-proxy';

export const PUT = proxyPut('/api/settings/{section}', {
  errorMessage: 'Failed to update settings',
});
