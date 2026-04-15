import { proxyGet } from '@/lib/api-proxy'

export const GET = proxyGet('/api/ml/predictions/progress', {
  errorMessage: 'Failed to fetch prediction progress',
})
