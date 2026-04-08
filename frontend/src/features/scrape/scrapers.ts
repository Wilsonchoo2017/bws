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
        label: 'LEGO Shop MY',
        url: 'https://shopee.com.my/legoshopmy',
        description: 'Official LEGO Shop Malaysia on Shopee'
      },
      {
        id: 'brickssmart',
        label: 'Bricks Smart',
        url: 'https://shopee.com.my/brickssmart',
        description: 'Bricks Smart LEGO shop on Shopee'
      },
      {
        id: 'brickandblock',
        label: 'Brick and Block',
        url: 'https://shopee.com.my/brick.and.block',
        description: 'Brick and Block LEGO shop on Shopee'
      },
      {
        id: 'mightyutan-shopee',
        label: 'Mighty Utan (Shopee)',
        url: 'https://shopee.com.my/mightyutan.os?shopCollection=269243899#product_list',
        description: 'Mighty Utan LEGO collection on Shopee'
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
    id: 'shopee_saturation',
    name: 'Shopee Saturation',
    description:
      'Check market saturation on Shopee for items with retail pricing',
    targets: [
      {
        id: 'batch',
        label: 'All Items (Batch)',
        url: 'batch',
        description: 'Check all items with RRP that haven\'t been checked recently'
      }
    ]
  },
  {
    id: 'shopee_competition',
    name: 'Shopee Competition',
    description:
      'Track competing sellers on Shopee for portfolio items with per-listing snapshots',
    targets: [
      {
        id: 'batch',
        label: 'All Portfolio Items (Batch)',
        url: 'batch',
        description: 'Check all portfolio holdings that haven\'t been checked recently'
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
