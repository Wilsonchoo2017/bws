import { Inter, Geist_Mono } from 'next/font/google';
import localFont from 'next/font/local';
import { cn } from '@/lib/utils';

const fontInter = Inter({
  subsets: ['latin'],
  variable: '--font-inter'
});

const fontMono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-mono'
});

const fontSatoshi = localFont({
  src: [
    {
      path: '../../public/fonts/Satoshi-Light.woff2',
      weight: '300',
      style: 'normal'
    },
    {
      path: '../../public/fonts/Satoshi-Regular.woff2',
      weight: '400',
      style: 'normal'
    },
    {
      path: '../../public/fonts/Satoshi-Medium.woff2',
      weight: '500',
      style: 'normal'
    },
    {
      path: '../../public/fonts/Satoshi-Bold.woff2',
      weight: '700',
      style: 'normal'
    },
    {
      path: '../../public/fonts/Satoshi-Black.woff2',
      weight: '900',
      style: 'normal'
    }
  ],
  variable: '--font-satoshi',
  display: 'swap'
});

export const fontVariables = cn(
  fontInter.variable,
  fontSatoshi.variable,
  fontMono.variable
);
