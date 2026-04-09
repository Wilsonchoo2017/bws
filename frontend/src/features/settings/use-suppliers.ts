'use client';

import { useCallback, useEffect, useState } from 'react';

export function useSuppliers(): {
  suppliers: string[];
  loading: boolean;
  refetch: () => void;
} {
  const [suppliers, setSuppliers] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchSuppliers = useCallback(async () => {
    try {
      const res = await fetch('/api/settings');
      const json = await res.json();
      if (json.success && Array.isArray(json.data.suppliers)) {
        setSuppliers(json.data.suppliers);
      }
    } catch {
      // silently fail -- forms still work with empty list
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSuppliers();
  }, [fetchSuppliers]);

  return { suppliers, loading, refetch: fetchSuppliers };
}
