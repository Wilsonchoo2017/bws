'use client';

import { useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { usePlatforms } from '@/features/settings/use-platforms';
import { useSuppliers } from '@/features/settings/use-suppliers';
import type { Transaction } from './types';

interface EditTransactionFormProps {
  transaction: Transaction;
  onSave: (updated: Transaction) => void;
  onCancel: () => void;
}

export function EditTransactionForm({
  transaction,
  onSave,
  onCancel,
}: EditTransactionFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);

  const [txnType, setTxnType] = useState<'BUY' | 'SELL'>(
    transaction.txn_type as 'BUY' | 'SELL'
  );
  const [quantity, setQuantity] = useState(String(transaction.quantity));
  const [priceRM, setPriceRM] = useState(
    (transaction.price_cents / 100).toFixed(2)
  );
  const [txnDate, setTxnDate] = useState(
    new Date(transaction.txn_date).toISOString().split('T')[0]
  );
  const [notes, setNotes] = useState(transaction.notes ?? '');
  const [supplier, setSupplier] = useState(transaction.supplier ?? '');
  const [platform, setPlatform] = useState(transaction.platform ?? '');
  const { suppliers: supplierOptions } = useSuppliers();
  const { platforms: platformOptions } = usePlatforms();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    setSubmitting(true);

    const priceCents = Math.round(parseFloat(priceRM) * 100);
    if (isNaN(priceCents) || priceCents <= 0) {
      setError('Invalid price');
      setSubmitting(false);
      submittingRef.current = false;
      return;
    }

    const body: Record<string, unknown> = {};
    if (txnType !== transaction.txn_type) body.txn_type = txnType;
    if (parseInt(quantity, 10) !== transaction.quantity)
      body.quantity = parseInt(quantity, 10);
    if (priceCents !== transaction.price_cents) body.price_cents = priceCents;
    const newDate = new Date(txnDate).toISOString();
    if (newDate !== new Date(transaction.txn_date).toISOString())
      body.txn_date = newDate;
    const trimmedNotes = notes.trim() || null;
    if (trimmedNotes !== (transaction.notes ?? null)) {
      if (trimmedNotes === null) {
        body.clear_notes = true;
      } else {
        body.notes = trimmedNotes;
      }
    }
    const trimmedSupplier = supplier.trim() || null;
    if (trimmedSupplier !== (transaction.supplier ?? null)) {
      if (trimmedSupplier === null) {
        body.clear_supplier = true;
      } else {
        body.supplier = trimmedSupplier;
      }
    }
    const trimmedPlatform = platform.trim() || null;
    if (trimmedPlatform !== (transaction.platform ?? null)) {
      if (trimmedPlatform === null) {
        body.clear_platform = true;
      } else {
        body.platform = trimmedPlatform;
      }
    }

    if (Object.keys(body).length === 0) {
      onCancel();
      return;
    }

    try {
      const res = await fetch(
        `/api/portfolio/transactions/${transaction.id}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );

      const data = await res.json();
      if (!data.success) {
        setError(data.error || 'Failed to update transaction');
      } else {
        onSave(data.data);
      }
    } catch {
      setError('Network error');
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className='rounded-lg border p-4 space-y-3'>
      <div className='flex items-center justify-between'>
        <h3 className='text-sm font-semibold'>
          Edit Transaction #{transaction.id} &mdash; {transaction.set_number}
        </h3>
        <Button type='button' variant='ghost' size='sm' onClick={onCancel}>
          Cancel
        </Button>
      </div>

      {error && <p className='text-destructive text-sm'>{error}</p>}

      <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
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
          <label className='text-muted-foreground text-xs'>
            Price/Unit (RM)
          </label>
          <input
            type='number'
            required
            min={0.01}
            step={0.01}
            value={priceRM}
            onChange={(e) => setPriceRM(e.target.value)}
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
        <div>
          <label className='text-muted-foreground text-xs'>Supplier</label>
          <select
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          >
            <option value=''>Select supplier...</option>
            {supplier && !supplierOptions.includes(supplier) && (
              <option value={supplier}>{supplier}</option>
            )}
            {supplierOptions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <label className='text-muted-foreground text-xs'>Platform</label>
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          >
            <option value=''>Select platform...</option>
            {platform && !platformOptions.includes(platform) && (
              <option value={platform}>{platform}</option>
            )}
            {platformOptions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
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

      <div className='flex gap-2'>
        <Button type='submit' size='sm' disabled={submitting}>
          {submitting ? 'Saving...' : 'Save Changes'}
        </Button>
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
