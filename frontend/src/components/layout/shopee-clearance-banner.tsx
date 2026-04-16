'use client';

import {
  formatCountdown,
  useShopeeClearance,
} from '@/features/operations/use-shopee-clearance';

export function ShopeeClearanceBanner() {
  const { clearance, solveStatus, solving, countdown, handleSolve } =
    useShopeeClearance({ pollIntervalMs: 30_000 });

  // Don't render until we have clearance data
  if (clearance === null) return null;

  // Valid clearance -- hide banner entirely
  if (clearance.valid && !solving) {
    return null;
  }

  // Solving in progress
  if (solving && solveStatus) {
    const label =
      solveStatus.status === 'launching'
        ? 'Launching browser...'
        : solveStatus.status === 'waiting_for_user'
          ? 'Solve the captcha in the browser window'
          : solveStatus.status === 'verifying'
            ? 'Verifying...'
            : 'Processing...';

    return (
      <div className='border-b border-amber-200 bg-amber-50 px-6 py-2 dark:border-amber-800 dark:bg-amber-950/30'>
        <div className='flex items-center gap-3'>
          <div className='h-2 w-2 animate-pulse rounded-full bg-amber-500' />
          <p className='text-sm font-medium text-amber-800 dark:text-amber-200'>
            {label}
          </p>
        </div>
      </div>
    );
  }

  // Solve failed
  if (solveStatus?.status === 'failed') {
    return (
      <div className='border-b border-red-200 bg-red-50 px-6 py-2 dark:border-red-800 dark:bg-red-950/30'>
        <div className='flex items-center justify-between'>
          <p className='text-sm text-red-800 dark:text-red-200'>
            Captcha solve failed: {solveStatus.error?.slice(0, 200)}
          </p>
          <button
            onClick={handleSolve}
            disabled={solving}
            className='rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50'
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // No clearance -- prominent red banner
  return (
    <div className='border-b border-red-200 bg-red-50 px-6 py-2 dark:border-red-800 dark:bg-red-950/30'>
      <div className='flex items-center justify-between'>
        <p className='text-sm text-red-800 dark:text-red-200'>
          Shopee jobs blocked -- no captcha clearance
        </p>
        <button
          onClick={handleSolve}
          disabled={solving}
          className='rounded bg-red-600 px-3 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50'
        >
          Solve Captcha
        </button>
      </div>
    </div>
  );
}
