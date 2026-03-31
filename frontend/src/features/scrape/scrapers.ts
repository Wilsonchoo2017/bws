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
  },
  {
    id: 'toysrus',
    name: 'Toys"R"Us Malaysia',
    description:
      'Scrape LEGO catalog from toysrus.com.my via Demandware API',
    targets: [
      {
        id: 'lego-catalog',
        label: 'LEGO Full Catalog',
        url: 'https://www.toysrus.com.my/lego/',
        description: 'Full LEGO product catalog on Toys"R"Us Malaysia'
      }
    ]
  },
  {
    id: 'mightyutan',
    name: 'Mighty Utan Malaysia',
    description:
      'Scrape LEGO catalog from mightyutan.com.my via SiteGiant storefront',
    targets: [
      {
        id: 'lego-catalog',
        label: 'LEGO Full Catalog',
        url: 'https://mightyutan.com.my/collection/lego-1',
        description: 'Full LEGO product catalog on Mighty Utan Malaysia'
      }
    ]
  },
  {
    id: 'bricklink_catalog',
    name: 'BrickLink Catalog',
    description:
      'Discover items from BrickLink catalog list pages with full pagination',
    targets: []
  }
];

export function getScraperById(id: string): ScraperConfig | undefined {
  return SCRAPERS.find((s) => s.id === id);
}
