/** @type {import('next').NextConfig} */
const path = require('path');

const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  async rewrites() {
    return [
      { source: '/api/:path*', destination: 'http://127.0.0.1:8000/api/:path*' },
      { source: '/health', destination: 'http://127.0.0.1:8000/health' },
      { source: '/auth/:path*', destination: 'http://127.0.0.1:8000/auth/:path*' },
    ];
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      '@jarvis/sdk': path.resolve(__dirname, '../packages/sdk/src'),
      '@jarvis/ui': path.resolve(__dirname, '../packages/ui/src'),
    };
    return config;
  },
};

module.exports = nextConfig;
