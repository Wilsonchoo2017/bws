import Link from 'next/link';
import { SCRAPERS } from '@/features/scrape/scrapers';

export default function ScrapePage() {
  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>Scrapers</h1>
        <p className='text-muted-foreground text-sm'>
          Browser automation scrapers for LEGO market data.
        </p>
      </div>

      <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
        {SCRAPERS.map((scraper) => (
          <Link
            key={scraper.id}
            href={`/scrape/${scraper.id}`}
            className='border-border hover:border-primary/50 hover:bg-accent/50 rounded-lg border p-6 transition-colors'
          >
            <h2 className='text-lg font-semibold'>{scraper.name}</h2>
            <p className='text-muted-foreground mt-1 text-sm'>
              {scraper.description}
            </p>
            <div className='mt-4 flex items-center gap-2'>
              <span className='text-muted-foreground text-xs'>
                {scraper.targets.length} target
                {scraper.targets.length !== 1 ? 's' : ''}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
