/** @type {import('next').NextConfig} */
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
};

module.exports = nextConfig;
