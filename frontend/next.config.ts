import type { NextConfig } from 'next';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'img.bricklink.com',
        port: ''
      }
    ]
  },
  async rewrites() {
    return [
      {
        // Proxy local image serving to the Python backend
        source: '/api/images/:asset_type/:item_id',
        destination: `${API_BASE}/api/images/:asset_type/:item_id`,
      },
    ];
  },
  transpilePackages: ['geist'],
  serverExternalPackages: ['@duckdb/node-api', '@duckdb/node-bindings']
};

export default nextConfig;
