'use client';

import { useCallback, useEffect, useState } from 'react';

export function usePlatforms(): {
  platforms: string[];
  loading: boolean;
  refetch: () => void;
} {
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPlatforms = useCallback(async () => {
    try {
      const res = await fetch('/api/settings');
      const json = await res.json();
      if (json.success && Array.isArray(json.data.platforms)) {
        setPlatforms(json.data.platforms);
      }
    } catch {
      // silently fail -- forms still work with empty list
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlatforms();
  }, [fetchPlatforms]);

  return { platforms, loading, refetch: fetchPlatforms };
}
