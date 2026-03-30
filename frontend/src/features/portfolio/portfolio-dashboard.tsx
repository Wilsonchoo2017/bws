'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useState } from 'react';
import { EnrichPortfolioButton } from './enrich-portfolio-button';
import { PortfolioSummaryCards } from './portfolio-summary-cards';
import { HoldingsTable } from './holdings-table';
import { AddTransactionForm } from './add-transaction-form';

export function PortfolioDashboard() {
  const router = useRouter();
  const [refreshKey, setRefreshKey] = useState(0);

  const handleTxnAdded = useCallback(() => {
    setRefreshKey((k) => k + 1);
    router.refresh();
  }, [router]);

  return (
    <div className='flex flex-1 flex-col gap-6' key={refreshKey}>
      <PortfolioSummaryCards />
      <div className='flex items-center justify-between'>
        <div className='flex items-center gap-4'>
          <h2 className='text-lg font-semibold'>Holdings</h2>
          <Link
            href='/portfolio/transactions'
            className='text-muted-foreground text-sm hover:underline'
          >
            View all transactions
          </Link>
        </div>
        <div className='flex items-center gap-2'>
          <EnrichPortfolioButton />
          <AddTransactionForm onSuccess={handleTxnAdded} />
        </div>
      </div>
      <HoldingsTable />
    </div>
  );
}
