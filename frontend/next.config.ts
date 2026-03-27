import type { NextConfig } from 'next';

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
  transpilePackages: ['geist'],
  serverExternalPackages: ['@duckdb/node-api', '@duckdb/node-bindings']
};

export default nextConfig;
