import type { Metadata, Viewport } from 'next';
import '@/styles/globals.css';
import ClientShell from './ClientShell';

export const metadata: Metadata = {
  title: 'JARVIS — Neural OS',
  description: 'Personal AI Operating System',
  manifest: '/manifest.json',
};

export const viewport: Viewport = {
  themeColor: '#00d4ff',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="theme-sky">
      <body>
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
