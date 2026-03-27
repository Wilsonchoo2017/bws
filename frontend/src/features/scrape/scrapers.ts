import type { ScraperConfig } from './types';

export const SCRAPERS: ScraperConfig[] = [
  {
    id: 'shopee',
    name: 'Shopee Malaysia',
    description:
      'Scrape LEGO products from Shopee.com.my shops and collections',
    targets: [
      {
        id: 'legoshopmy',
        label: 'LEGO Shop MY - Full Collection',
        url: 'https://shopee.com.my/legoshopmy?page=0&shopCollection=258084132',
        description: 'Official LEGO Shop Malaysia collection on Shopee'
      }
    ]
  }
];

export function getScraperById(id: string): ScraperConfig | undefined {
  return SCRAPERS.find((s) => s.id === id);
}
