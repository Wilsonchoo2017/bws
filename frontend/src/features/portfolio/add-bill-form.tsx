'use client';

import { useRef, useState, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import type { Transaction } from './types';

interface LineItem {
  setNumber: string;
  quantity: string;
  unitPrice: string;
  lineTotal: string;
  lastEdited: 'unit' | 'total';
}

const emptyLine = (): LineItem => ({
  setNumber: '',
  quantity: '1',
  unitPrice: '',
  lineTotal: '',
  lastEdited: 'unit',
});

export interface BillEditData {
  billId: string;
  transactions: Transaction[];
}

interface AddBillFormProps {
  onSuccess?: () => void;
  editData?: BillEditData;
  onCancel?: () => void;
}

function txnsToLineItems(txns: Transaction[]): LineItem[] {
  return txns.map((t) => ({
    setNumber: t.set_number,
    quantity: String(t.quantity),
    unitPrice: (t.price_cents / 100).toFixed(2),
    lineTotal: ((t.price_cents * t.quantity) / 100).toFixed(2),
    lastEdited: 'unit' as const,
  }));
}

function txnsFinalAmount(txns: Transaction[]): string {
  const total = txns.reduce((s, t) => s + t.price_cents * t.quantity, 0);
  return (total / 100).toFixed(2);
}

export function AddBillForm({ onSuccess, editData, onCancel }: AddBillFormProps) {
  const isEdit = !!editData;

  const [open, setOpen] = useState(isEdit);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);

  const [items, setItems] = useState<LineItem[]>(
    isEdit ? txnsToLineItems(editData.transactions) : [emptyLine()]
  );
  const [finalAmount, setFinalAmount] = useState(
    isEdit ? txnsFinalAmount(editData.transactions) : ''
  );
  const [txnDate, setTxnDate] = useState(
    isEdit
      ? new Date(editData.transactions[0].txn_date).toISOString().split('T')[0]
      : new Date().toISOString().split('T')[0]
  );
  const [condition, setCondition] = useState<'new' | 'used'>(
    isEdit ? editData.transactions[0].condition : 'new'
  );
  const [notes, setNotes] = useState(
    isEdit ? editData.transactions[0].notes ?? '' : ''
  );
  const [supplier, setSupplier] = useState(
    isEdit ? editData.transactions[0].supplier ?? '' : ''
  );

  const resetForm = () => {
    setItems([emptyLine()]);
    setFinalAmount('');
    setTxnDate(new Date().toISOString().split('T')[0]);
    setCondition('new');
    setNotes('');
    setSupplier('');
    setError(null);
  };

  const handleClose = () => {
    if (isEdit) {
      onCancel?.();
    } else {
      setOpen(false);
      resetForm();
    }
  };

  const updateItem = (index: number, field: keyof LineItem, value: string) => {
    setItems((prev) =>
      prev.map((item, i) => {
        if (i !== index) return item;
        const updated = { ...item, [field]: value };
        const qty = parseInt(updated.quantity, 10) || 0;

        if (field === 'unitPrice') {
          updated.lastEdited = 'unit';
          const unitCents = Math.round(parseFloat(value) * 100) || 0;
          updated.lineTotal = qty > 0 && unitCents > 0
            ? ((qty * unitCents) / 100).toFixed(2)
            : '';
        } else if (field === 'lineTotal') {
          updated.lastEdited = 'total';
          const totalCents = Math.round(parseFloat(value) * 100) || 0;
          updated.unitPrice = qty > 0 && totalCents > 0
            ? ((totalCents / qty) / 100).toFixed(2)
            : '';
        } else if (field === 'quantity') {
          // Recompute based on whichever was last edited
          if (updated.lastEdited === 'unit') {
            const unitCents = Math.round(parseFloat(updated.unitPrice) * 100) || 0;
            updated.lineTotal = qty > 0 && unitCents > 0
              ? ((qty * unitCents) / 100).toFixed(2)
              : '';
          } else {
            const totalCents = Math.round(parseFloat(updated.lineTotal) * 100) || 0;
            updated.unitPrice = qty > 0 && totalCents > 0
              ? ((totalCents / qty) / 100).toFixed(2)
              : '';
          }
        }
        return updated;
      })
    );
  };

  const addLine = () => {
    setItems((prev) => [...prev, emptyLine()]);
  };

  const removeLine = (index: number) => {
    setItems((prev) => prev.filter((_, i) => i !== index));
  };

  const subtotalCents = useMemo(() => {
    return items.reduce((sum, item) => {
      const qty = parseInt(item.quantity, 10) || 0;
      const price = Math.round(parseFloat(item.unitPrice) * 100) || 0;
      return sum + qty * price;
    }, 0);
  }, [items]);

  const finalAmountCents = useMemo(() => {
    const parsed = Math.round(parseFloat(finalAmount) * 100);
    return isNaN(parsed) || finalAmount.trim() === '' ? subtotalCents : parsed;
  }, [finalAmount, subtotalCents]);

  const adjustmentPct = useMemo(() => {
    if (subtotalCents <= 0 || finalAmountCents <= 0) return null;
    return ((finalAmountCents - subtotalCents) / subtotalCents) * 100;
  }, [subtotalCents, finalAmountCents]);

  const effectivePrices = useMemo(() => {
    if (subtotalCents <= 0 || finalAmountCents <= 0) return null;
    const ratio = finalAmountCents / subtotalCents;
    return items.map((item) => {
      const unitCents = Math.round(parseFloat(item.unitPrice) * 100) || 0;
      return Math.round(unitCents * ratio);
    });
  }, [items, subtotalCents, finalAmountCents]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    setSubmitting(true);

    const parsedItems = items.map((item) => ({
      set_number: item.setNumber.trim(),
      quantity: parseInt(item.quantity, 10),
      unit_price_cents: Math.round(parseFloat(item.unitPrice) * 100),
    }));

    const invalid = parsedItems.some(
      (p) =>
        !p.set_number ||
        isNaN(p.quantity) ||
        p.quantity <= 0 ||
        isNaN(p.unit_price_cents) ||
        p.unit_price_cents <= 0
    );
    if (invalid) {
      setError('All line items must have a valid set number, quantity, and either price/unit or line total');
      setSubmitting(false);
      submittingRef.current = false;
      return;
    }

    const submitFinalCents = finalAmount.trim() === '' ? subtotalCents : finalAmountCents;
    if (submitFinalCents <= 0) {
      setError('Final amount must be positive');
      setSubmitting(false);
      submittingRef.current = false;
      return;
    }

    const body = {
      items: parsedItems,
      final_amount_cents: submitFinalCents,
      txn_date: new Date(txnDate).toISOString(),
      condition,
      notes: notes.trim() || null,
      supplier: supplier.trim() || null,
    };

    const url = isEdit
      ? `/api/portfolio/transactions/bill/${editData.billId}`
      : '/api/portfolio/transactions/bill';
    const method = isEdit ? 'PUT' : 'POST';

    try {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await res.json();
      if (!data.success) {
        setError(data.error || `Failed to ${isEdit ? 'update' : 'create'} bill`);
      } else {
        if (!isEdit) resetForm();
        setOpen(false);
        onSuccess?.();
      }
    } catch {
      setError('Network error');
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)} size='sm'>
        Add Bill
      </Button>
    );
  }

  const fmt = (cents: number) => (cents / 100).toFixed(2);

  return (
    <form
      onSubmit={handleSubmit}
      className='rounded-lg border p-4 space-y-3'
    >
      <div className='flex items-center justify-between'>
        <h3 className='text-sm font-semibold'>
          {isEdit ? `Edit Bill (${editData.billId})` : 'New Bill'}
        </h3>
        <Button
          type='button'
          variant='ghost'
          size='sm'
          onClick={handleClose}
        >
          Cancel
        </Button>
      </div>

      {error && <p className='text-destructive text-sm'>{error}</p>}

      {/* Shared fields */}
      <div className='grid grid-cols-2 gap-3 sm:grid-cols-4'>
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
          <label className='text-muted-foreground text-xs'>Condition</label>
          <select
            value={condition}
            onChange={(e) => setCondition(e.target.value as 'new' | 'used')}
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          >
            <option value='new'>New</option>
            <option value='used'>Used</option>
          </select>
        </div>
        <div>
          <label className='text-muted-foreground text-xs'>Supplier</label>
          <input
            type='text'
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
            placeholder='Shopee, Lazada...'
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          />
        </div>
        <div>
          <label className='text-muted-foreground text-xs'>Notes</label>
          <input
            type='text'
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder='Shopee order #...'
            className='border-input bg-background mt-1 w-full rounded border px-2 py-1.5 text-sm'
          />
        </div>
      </div>

      {/* Line items header */}
      <div className='grid grid-cols-[1fr_60px_100px_100px_32px] gap-2 text-xs text-muted-foreground'>
        <span>Set #</span>
        <span>Qty</span>
        <span>Price/Unit (RM)</span>
        <span className='text-right'>Line Total (RM)</span>
        <span />
      </div>

      {/* Line items */}
      {items.map((item, i) => (
        <div
          key={i}
          className='grid grid-cols-[1fr_60px_100px_100px_32px] gap-2 items-center'
        >
          <input
            type='text'
            required
            pattern='^\d{3,6}(-\d+)?$'
            value={item.setNumber}
            onChange={(e) => updateItem(i, 'setNumber', e.target.value)}
            placeholder='75192'
            className='border-input bg-background rounded border px-2 py-1.5 text-sm'
          />
          <input
            type='number'
            required
            min={1}
            value={item.quantity}
            onChange={(e) => updateItem(i, 'quantity', e.target.value)}
            className='border-input bg-background rounded border px-2 py-1.5 text-sm'
          />
          <input
            type='number'
            min={0.01}
            step={0.01}
            value={item.unitPrice}
            onChange={(e) => updateItem(i, 'unitPrice', e.target.value)}
            placeholder='299.90'
            className='border-input bg-background rounded border px-2 py-1.5 text-sm'
          />
          <input
            type='number'
            min={0.01}
            step={0.01}
            value={item.lineTotal}
            onChange={(e) => updateItem(i, 'lineTotal', e.target.value)}
            placeholder='299.90'
            className='border-input bg-background rounded border px-2 py-1.5 text-sm text-right tabular-nums'
          />
          <button
            type='button'
            onClick={() => removeLine(i)}
            disabled={items.length <= 1}
            className='text-muted-foreground hover:text-destructive disabled:opacity-30 text-sm'
            title='Remove line'
          >
            x
          </button>
        </div>
      ))}

      {/* Subtotal row */}
      <div className='grid grid-cols-[1fr_60px_100px_100px_32px] gap-2 items-center'>
        <button
          type='button'
          onClick={addLine}
          className='text-muted-foreground hover:text-foreground text-xs text-left'
        >
          + Add line
        </button>
        <span />
        <span className='text-xs text-muted-foreground text-right'>Subtotal:</span>
        <span className='text-right text-sm font-medium tabular-nums'>
          {subtotalCents > 0 ? `RM${fmt(subtotalCents)}` : '-'}
        </span>
        <span />
      </div>

      {/* Final amount */}
      <div className='grid grid-cols-[1fr_60px_100px_100px_32px] gap-2 items-center border-t pt-3'>
        <span />
        <span />
        <label className='text-xs text-muted-foreground text-right'>
          Final Paid (RM):
        </label>
        <input
          type='number'
          min={0.01}
          step={0.01}
          value={finalAmount}
          onChange={(e) => setFinalAmount(e.target.value)}
          placeholder={subtotalCents > 0 ? fmt(subtotalCents) : '0.00'}
          className='border-input bg-background rounded border px-2 py-1.5 text-sm text-right tabular-nums'
        />
        <span />
      </div>

      {/* Adjustment preview */}
      {adjustmentPct !== null && (
        <div className='rounded bg-muted/50 p-3 space-y-1'>
          <div className='flex items-center justify-between text-xs'>
            <span className='text-muted-foreground'>Adjustment:</span>
            <span
              className={
                adjustmentPct < 0
                  ? 'text-green-600'
                  : adjustmentPct > 0
                    ? 'text-red-600'
                    : ''
              }
            >
              {adjustmentPct > 0 ? '+' : ''}
              {adjustmentPct.toFixed(2)}% (RM
              {fmt(Math.abs(finalAmountCents - subtotalCents))}{' '}
              {adjustmentPct < 0 ? 'discount' : 'extra'})
            </span>
          </div>
          {effectivePrices && (
            <div className='space-y-0.5'>
              {items.map((item, i) => {
                const origCents =
                  Math.round(parseFloat(item.unitPrice) * 100) || 0;
                const effCents = effectivePrices[i];
                if (!item.setNumber || origCents <= 0) return null;
                return (
                  <div
                    key={i}
                    className='flex justify-between text-xs tabular-nums'
                  >
                    <span>{item.setNumber}:</span>
                    <span>
                      RM{fmt(effCents)}/unit{' '}
                      <span className='text-muted-foreground'>
                        (was RM{fmt(origCents)})
                      </span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      <Button type='submit' size='sm' disabled={submitting}>
        {submitting ? 'Saving...' : isEdit ? 'Update Bill' : 'Save Bill'}
      </Button>
    </form>
  );
}
