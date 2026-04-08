import { CartTable } from '@/features/cart/cart-table';

export default function CartPage() {
  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>Cart</h1>
        <p className='text-muted-foreground text-sm'>
          Items auto-selected by configurable criteria, plus manually added items.
        </p>
      </div>
      <CartTable />
    </div>
  );
}
