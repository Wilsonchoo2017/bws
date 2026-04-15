import Link from 'next/link';

import { MlStatusBadge } from './ml-status-badge';
import { PredictionProgressBadge } from './prediction-progress-badge';

const NAV_ITEMS = [
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/items', label: 'Items' },
  { href: '/cart', label: 'Cart' },
  { href: '/scrape', label: 'Scrape' },
  { href: '/operations', label: 'Operations' },
];

export function Nav() {
  return (
    <nav className='border-border flex items-center gap-6 border-b px-6 py-3'>
      <Link href='/' className='font-heading text-lg font-bold'>
        BWS
      </Link>
      <div className='flex items-center gap-4'>
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className='text-muted-foreground hover:text-foreground text-sm transition-colors'
          >
            {item.label}
          </Link>
        ))}
      </div>
      <div className='ml-auto flex items-center gap-3'>
        <PredictionProgressBadge />
        <MlStatusBadge />
      </div>
    </nav>
  );
}
