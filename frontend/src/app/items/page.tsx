import { ItemsTable } from '@/features/items/items-table';

export default function ItemsPage() {
  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>LEGO Items</h1>
        <p className='text-muted-foreground text-sm'>
          Track and analyze LEGO sets, minifigures, and parts for investment
          opportunities.
        </p>
      </div>
      <ItemsTable />
    </div>
  );
}
