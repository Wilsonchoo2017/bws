'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';

export function SuppliersManager() {
  const [suppliers, setSuppliers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newName, setNewName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchSuppliers = useCallback(async () => {
    try {
      const res = await fetch('/api/settings');
      const json = await res.json();
      if (json.success && Array.isArray(json.data.suppliers)) {
        setSuppliers(json.data.suppliers);
      }
    } catch {
      setError('Failed to load suppliers');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSuppliers();
  }, [fetchSuppliers]);

  const saveSuppliers = useCallback(async (updated: string[]) => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/settings/suppliers', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values: updated }),
      });
      const json = await res.json();
      if (json.success) {
        setSuppliers(json.data);
      } else {
        setError(json.error ?? 'Failed to save');
      }
    } catch {
      setError('Network error');
    } finally {
      setSaving(false);
    }
  }, []);

  const handleAdd = useCallback(() => {
    const trimmed = newName.trim();
    if (!trimmed) return;
    if (suppliers.includes(trimmed)) {
      setError(`"${trimmed}" already exists`);
      return;
    }
    setNewName('');
    saveSuppliers([...suppliers, trimmed]);
    inputRef.current?.focus();
  }, [newName, suppliers, saveSuppliers]);

  const handleDelete = useCallback(
    (name: string) => {
      saveSuppliers(suppliers.filter((s) => s !== name));
    },
    [suppliers, saveSuppliers]
  );

  if (loading) {
    return <p className='text-muted-foreground text-sm'>Loading suppliers...</p>;
  }

  return (
    <div className='rounded-lg border border-border p-4'>
      <h3 className='mb-3 text-sm font-semibold'>Suppliers</h3>

      {error && (
        <p className='mb-2 text-sm text-destructive'>
          {error}{' '}
          <button onClick={() => setError(null)} className='underline'>
            dismiss
          </button>
        </p>
      )}

      {suppliers.length === 0 ? (
        <p className='mb-3 text-sm text-muted-foreground'>
          No suppliers configured yet.
        </p>
      ) : (
        <ul className='mb-3 space-y-1'>
          {suppliers.map((name) => (
            <li
              key={name}
              className='flex items-center justify-between rounded border border-border px-3 py-1.5 text-sm'
            >
              <span>{name}</span>
              <button
                onClick={() => handleDelete(name)}
                disabled={saving}
                className='text-muted-foreground hover:text-destructive text-xs disabled:opacity-50'
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className='flex gap-2'>
        <input
          ref={inputRef}
          type='text'
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleAdd();
            }
          }}
          placeholder='Supplier name'
          className='border-input bg-background flex-1 rounded border px-2 py-1.5 text-sm'
        />
        <Button
          type='button'
          size='sm'
          onClick={handleAdd}
          disabled={saving || !newName.trim()}
        >
          {saving ? 'Saving...' : 'Add'}
        </Button>
      </div>
    </div>
  );
}
