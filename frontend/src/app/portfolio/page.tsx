import { PortfolioDashboard } from '@/features/portfolio/portfolio-dashboard';

export default function PortfolioPage() {
  return (
    <div className='flex h-screen flex-col p-6'>
      <div className='mb-6'>
        <h1 className='text-2xl font-bold tracking-tight'>Portfolio</h1>
        <p className='text-muted-foreground text-sm'>
          Track your LEGO investments, cost basis, and unrealized gains.
        </p>
      </div>
      <div className='flex min-h-0 flex-1 flex-col'>
        <PortfolioDashboard />
      </div>
    </div>
  );
}
