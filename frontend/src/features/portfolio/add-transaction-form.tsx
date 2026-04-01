'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

interface AddTransactionFormProps {
  onSuccess?: () => void;
}

export function AddTransactionForm({ onSuccess }: AddTransactionFormProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [setNumber, setSetNumber] = useState('');
  const [txnType, setTxnType] = useState<'BUY' | 'SELL'>('BUY');
  const [quantity, setQuantity] = useState('1');
  const [priceRM, setPriceRM] = useState('');
  const [txnDate, setTxnDate] = useState(
    new Date().toISOString().split('T')[0]
  );
  const [notes, setNotes] = useState('');

  const resetForm = () => {
    setSetNumber('');
    setTxnType('BUY');
    setQuantity('1');
    setPriceRM('');
    setTxnDate(new Date().toISOString().split('T')[0]);
    setNotes('');
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    const priceCents = Math.round(parseFloat(priceRM) * 100);
    if (isNaN(priceCents) || priceCents <= 0) {
      setError('Invalid price');
      setSubmitting(false);
      return;
    }

    try {
      const res = await fetch('/api/portfolio/transactions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          set_number: setNumber.trim(),
          txn_type: txnType,
          quantity: parseInt(quantity, 10),
          price_cents: priceCents,
          txn_date: new Date(txnDate).toISOString(),
          notes: notes.trim() || null,
        }),
      });

      const data = await res.json();
      if (!data.success) {
        setError(data.error || 'Failed to create transaction');
      } else {
        resetForm();
        setOpen(false);
        onSuccess?.();
      }
    } catch {
      setError('Network error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)} size='sm'>
        Add Transaction
      </Button>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className='rounded-lg border p-4 space-y-3'
    >
      <div className='flex items-center justify-between'>
        <h3 className='text-sm font-semibold'>New Transaction</h3>
        <Button
          type='button'
          variant='ghost'
          size='sm'
          onClick={() => {
            setOpen(false);
            resetForm();
          }}
        >
          Cancel
        </Button>
      </div>

      {error && (
        <p className='text-destructive text-sm'>{error}</p>
      )}

      <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
        <div>
          <label className='text-muted-foreground text-xs'>Set Number</label>
          <input
            type='text'
            required
            pattern='^\d{3,6}(-\d+)?$'
            value={setNumber}
            onChange={(e) => setSetNumber(e.target.value)}
            placeholder='75192'
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          />
        </div>
        <div>
          <label className='text-muted-foreground text-xs'>Type</label>
          <select
            value={txnType}
            onChange={(e) => setTxnType(e.target.value as 'BUY' | 'SELL')}
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          >
            <option value='BUY'>BUY</option>
            <option value='SELL'>SELL</option>
          </select>
        </div>
        <div>
          <label className='text-muted-foreground text-xs'>Quantity</label>
          <input
            type='number'
            required
            min={1}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          />
        </div>
        <div>
          <label className='text-muted-foreground text-xs'>Price/Unit (RM)</label>
          <input
            type='number'
            required
            min={0.01}
            step={0.01}
            value={priceRM}
            onChange={(e) => setPriceRM(e.target.value)}
            placeholder='299.90'
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          />
        </div>
        <div>
          <label className='text-muted-foreground text-xs'>Date</label>
          <input
            type='date'
            required
            value={txnDate}
            onChange={(e) => setTxnDate(e.target.value)}
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          />
        </div>
        <div className='col-span-2'>
          <label className='text-muted-foreground text-xs'>Notes</label>
          <input
            type='text'
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder='Optional notes'
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          />
        </div>
      </div>

      <Button type='submit' size='sm' disabled={submitting}>
        {submitting ? 'Saving...' : 'Save Transaction'}
      </Button>
    </form>
  );
}
