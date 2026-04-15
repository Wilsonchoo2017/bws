'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useState } from 'react';
import { DrawdownPanel } from './drawdown-panel';
import { EnrichPortfolioButton } from './enrich-portfolio-button';
import { PortfolioSummaryCards } from './portfolio-summary-cards';
import { HoldingsTable } from './holdings-table';
import { AddBillForm } from './add-bill-form';
import { SellBillForm } from './sell-bill-form';

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
      <DrawdownPanel />
      <div className='flex items-center justify-between'>
        <div className='flex items-center gap-4'>
          <Link
            href='/portfolio/transactions'
            className='text-muted-foreground text-sm hover:underline'
          >
            View all transactions
          </Link>
        </div>
        <div className='flex items-center gap-2'>
          <EnrichPortfolioButton />
          <SellBillForm onSuccess={handleTxnAdded} />
          <AddBillForm onSuccess={handleTxnAdded} />
        </div>
      </div>
      <HoldingsTable />
    </div>
  );
}
