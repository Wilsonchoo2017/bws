import { ShopeeItemsTable } from '@/features/items/shopee/shopee-items-table';

export default function ShopeeItemsPage() {
  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>Shopee Items</h1>
        <p className='text-muted-foreground text-sm'>
          LEGO products scraped from Shopee Malaysia.
        </p>
      </div>
      <ShopeeItemsTable />
    </div>
  );
}
