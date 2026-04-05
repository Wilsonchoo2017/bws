import { DataCoverage } from '@/features/stats/data-coverage';

export default function StatsPage() {
  return (
    <div className='mx-auto max-w-6xl px-6 py-8'>
      <DataCoverage />
    </div>
  );
}
