import { UnifiedItemsTable } from '@/features/items/unified-items-table';

export default function ItemsPage() {
  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>LEGO Items</h1>
        <p className='text-muted-foreground text-sm'>
          All LEGO products aggregated from Shopee, Bricklink, and other
          sources. Click a set number to see price history.
        </p>
      </div>
      <UnifiedItemsTable />
    </div>
  );
}
