'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';

export function PlatformsManager() {
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newName, setNewName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchPlatforms = useCallback(async () => {
    try {
      const res = await fetch('/api/settings');
      const json = await res.json();
      if (json.success && Array.isArray(json.data.platforms)) {
        setPlatforms(json.data.platforms);
      }
    } catch {
      setError('Failed to load platforms');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlatforms();
  }, [fetchPlatforms]);

  const savePlatforms = useCallback(async (updated: string[]) => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/settings/platforms', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values: updated }),
      });
      const json = await res.json();
      if (json.success) {
        setPlatforms(json.data);
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
    if (platforms.includes(trimmed)) {
      setError(`"${trimmed}" already exists`);
      return;
    }
    setNewName('');
    savePlatforms([...platforms, trimmed]);
    inputRef.current?.focus();
  }, [newName, platforms, savePlatforms]);

  const handleDelete = useCallback(
    (name: string) => {
      savePlatforms(platforms.filter((s) => s !== name));
    },
    [platforms, savePlatforms]
  );

  if (loading) {
    return <p className='text-muted-foreground text-sm'>Loading platforms...</p>;
  }

  return (
    <div className='rounded-lg border border-border p-4'>
      <h3 className='mb-3 text-sm font-semibold'>Selling Platforms</h3>

      {error && (
        <p className='mb-2 text-sm text-destructive'>
          {error}{' '}
          <button onClick={() => setError(null)} className='underline'>
            dismiss
          </button>
        </p>
      )}

      {platforms.length === 0 ? (
        <p className='mb-3 text-sm text-muted-foreground'>
          No platforms configured yet.
        </p>
      ) : (
        <ul className='mb-3 space-y-1'>
          {platforms.map((name) => (
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
          placeholder='Platform name'
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
