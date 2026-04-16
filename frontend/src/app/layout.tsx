import { Toaster } from '@/components/ui/sonner';
import { fontVariables } from '@/lib/font';
import ThemeProvider from '@/components/layout/ThemeToggle/theme-provider';
import { Nav } from '@/components/layout/nav';
import { ShopeeClearanceBanner } from '@/components/layout/shopee-clearance-banner';
import { cn } from '@/lib/utils';
import type { Metadata, Viewport } from 'next';
import './globals.css';

const META_THEME_COLORS = {
  light: '#ffffff',
  dark: '#09090b'
};

export const metadata: Metadata = {
  title: 'BWS - Brick Watch System',
  description: 'LEGO investment tracking and analysis'
};

export const viewport: Viewport = {
  themeColor: META_THEME_COLORS.light
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang='en' suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                if (localStorage.theme === 'dark' || ((!('theme' in localStorage) || localStorage.theme === 'system') && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.querySelector('meta[name="theme-color"]').setAttribute('content', '${META_THEME_COLORS.dark}')
                }
              } catch (_) {}
            `
          }}
        />
      </head>
      <body
        className={cn(
          'bg-background min-h-screen font-sans antialiased',
          fontVariables
        )}
      >
        <ThemeProvider
          attribute='class'
          defaultTheme='system'
          enableSystem
          disableTransitionOnChange
          enableColorScheme
        >
          <Nav />
          <ShopeeClearanceBanner />
          <Toaster />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
