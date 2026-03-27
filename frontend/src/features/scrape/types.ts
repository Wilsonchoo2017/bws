export interface Scraper {
  id: string;
  name: string;
  description: string;
  status: 'idle' | 'running' | 'error';
  lastRun: string | null;
  itemCount: number;
}

export interface ScraperConfig {
  id: string;
  name: string;
  description: string;
  targets: ScrapeTarget[];
}

export interface ScrapeTarget {
  id: string;
  label: string;
  url: string;
  description: string;
}

export interface ScrapeResult {
  success: boolean;
  query: string;
  items: ScrapeItem[];
  error?: string;
}

export interface ScrapeItem {
  title: string;
  price_display: string;
  sold_count: string | null;
  rating: string | null;
  shop_name: string | null;
  product_url: string | null;
  image_url: string | null;
}
