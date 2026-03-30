import Link from 'next/link';
import { TransactionsTable } from '@/features/portfolio/transactions-table';

export default function TransactionsPage() {
  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <div className='flex items-center gap-4'>
          <h1 className='text-2xl font-bold tracking-tight'>Transactions</h1>
          <Link
            href='/portfolio'
            className='text-muted-foreground text-sm hover:underline'
          >
            Back to Portfolio
          </Link>
        </div>
        <p className='text-muted-foreground text-sm'>
          Full history of all BUY and SELL transactions.
        </p>
      </div>
      <TransactionsTable />
    </div>
  );
}
