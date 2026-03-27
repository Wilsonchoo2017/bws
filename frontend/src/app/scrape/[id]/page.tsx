import { notFound } from 'next/navigation';
import { getScraperById } from '@/features/scrape/scrapers';
import { ScraperDashboard } from '@/features/scrape/scraper-dashboard';

export default async function ScraperPage({
  params
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const scraper = getScraperById(id);

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
