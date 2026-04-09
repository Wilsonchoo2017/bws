import { notFound } from 'next/navigation';
import type { ScraperConfig } from '@/features/scrape/types';
import { ScraperDashboard } from '@/features/scrape/scraper-dashboard';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

async function fetchScraper(id: string): Promise<ScraperConfig | null> {
  try {
    const res = await fetch(`${API_BASE}/api/scrape/scrapers/${id}`, {
      cache: 'no-store',
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function ScraperPage({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const scraper = await fetchScraper(id);

  if (!scraper) {
    notFound();
  }

  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>{scraper.name}</h1>
        <p className='text-muted-foreground text-sm'>{scraper.description}</p>
      </div>
      <ScraperDashboard scraper={scraper} />
    </div>
  );
}
