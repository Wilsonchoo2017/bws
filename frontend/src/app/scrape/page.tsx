import Link from 'next/link';
import type { ScraperConfig } from '@/features/scrape/types';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

const CATEGORY_ORDER: readonly string[] = [
  'retail',
  'marketplace',
  'market',
  'reference',
];

const CATEGORY_LABELS: Record<string, string> = {
  retail: 'Retail',
  marketplace: 'Marketplace',
  market: 'Market Analysis',
  reference: 'Reference Data',
};

function groupByCategory(
  scrapers: readonly ScraperConfig[],
): ReadonlyArray<{ readonly category: string; readonly items: readonly ScraperConfig[] }> {
  const groups = new Map<string, ScraperConfig[]>();
  for (const s of scrapers) {
    const cat = s.category ?? 'other';
    const list = groups.get(cat);
    if (list) {
      list.push(s);
    } else {
      groups.set(cat, [s]);
    }
  }
  return [...groups.entries()]
    .sort(([a], [b]) => {
      const ai = CATEGORY_ORDER.indexOf(a);
      const bi = CATEGORY_ORDER.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    })
    .map(([category, items]) => ({ category, items }));
}

async function fetchScrapers(): Promise<ScraperConfig[]> {
  try {
    const res = await fetch(`${API_BASE}/api/scrape/scrapers`, {
      cache: 'no-store',
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function ScrapePage() {
  const scrapers = await fetchScrapers();
  const groups = groupByCategory(scrapers);

  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>Scrapers</h1>
        <p className='text-muted-foreground text-sm'>
          Browser automation scrapers for LEGO market data.
        </p>
      </div>

      {scrapers.length === 0 ? (
        <p className='text-muted-foreground text-sm'>
          No scrapers available. Is the API server running?
        </p>
      ) : (
        <div className='flex flex-col gap-8'>
          {groups.map(({ category, items }) => (
            <section key={category}>
              <h2 className='text-muted-foreground mb-3 text-xs font-semibold uppercase tracking-wider'>
                {CATEGORY_LABELS[category] ?? category}
              </h2>
              <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-3'>
                {items.map((scraper) => (
                  <Link
                    key={scraper.id}
                    href={`/scrape/${scraper.id}`}
                    className='border-border hover:border-primary/50 hover:bg-accent/50 rounded-lg border p-6 transition-colors'
                  >
                    <h3 className='text-lg font-semibold'>{scraper.name}</h3>
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
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
