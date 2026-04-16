'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export interface ClearanceStatus {
  valid: boolean;
  cleared_at?: string;
  expires_at?: string;
  remaining_seconds?: number;
  method?: string;
}

export interface SolveStatus {
  status: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  clearance_id?: number;
  captcha_detected?: boolean;
}

const ACTIVE_SOLVE_STATUSES = new Set([
  'launching',
  'waiting_for_user',
  'verifying',
]);

export function formatCountdown(seconds: number): string {
  if (seconds <= 0) return '0s';
  const totalSeconds = Math.ceil(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

interface UseShopeeClearanceOptions {
  /** Interval in ms for polling clearance status. */
  pollIntervalMs?: number;
}

export function useShopeeClearance(opts: UseShopeeClearanceOptions = {}) {
  const { pollIntervalMs = 30_000 } = opts;

  const [clearance, setClearance] = useState<ClearanceStatus | null>(null);
  const [solveStatus, setSolveStatus] = useState<SolveStatus | null>(null);
  const [solving, setSolving] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const solveRef = useRef<NodeJS.Timeout | null>(null);
  const countdownRef = useRef<NodeJS.Timeout | null>(null);
  const expiresAtRef = useRef<number>(0);

  const fetchClearance = useCallback(async () => {
    try {
      const res = await fetch('/api/scrape/shopee/captcha-clearance/status');
      if (!res.ok) return;
      const data: ClearanceStatus = await res.json();
      setClearance(data);
      if (data.valid && data.remaining_seconds) {
        expiresAtRef.current = Date.now() + data.remaining_seconds * 1000;
        setCountdown(data.remaining_seconds);
      } else {
        expiresAtRef.current = 0;
        setCountdown(0);
      }
    } catch {
      // Backend may be down
    }
  }, []);

  const fetchSolveStatus = useCallback(async () => {
    try {
      const res = await fetch(
        '/api/scrape/shopee/captcha-clearance/solve-status'
      );
      if (!res.ok) return;
      const data: SolveStatus = await res.json();
      setSolveStatus(data);

      if (ACTIVE_SOLVE_STATUSES.has(data.status)) {
        setSolving(true);
      } else {
        setSolving(false);
        if (data.status === 'completed') {
          fetchClearance();
        }
      }
    } catch {
      setSolving(false);
    }
  }, [fetchClearance]);

  // Poll clearance status
  useEffect(() => {
    fetchClearance();
    pollRef.current = setInterval(fetchClearance, pollIntervalMs);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchClearance, pollIntervalMs]);

  // Poll solve status while solving (every 2s)
  useEffect(() => {
    if (!solving) {
      if (solveRef.current) clearInterval(solveRef.current);
      return;
    }
    solveRef.current = setInterval(fetchSolveStatus, 2_000);
    return () => {
      if (solveRef.current) clearInterval(solveRef.current);
    };
  }, [solving, fetchSolveStatus]);

  // Countdown tick -- compute from stored expiry to avoid drift
  useEffect(() => {
    if (countdown <= 0) return;
    countdownRef.current = setTimeout(() => {
      const remaining = Math.max(
        0,
        Math.round((expiresAtRef.current - Date.now()) / 1000)
      );
      setCountdown(remaining);
    }, 1000);
    return () => {
      if (countdownRef.current) clearTimeout(countdownRef.current);
    };
  }, [countdown]);

  const handleSolve = useCallback(async () => {
    setSolveStatus(null);
    try {
      const res = await fetch('/api/scrape/shopee/captcha-clearance/solve', {
        method: 'POST',
      });
      if (res.ok) {
        setSolving(true);
        fetchSolveStatus();
      }
    } catch {
      // ignore
    }
  }, [fetchSolveStatus]);

  return {
    clearance,
    solveStatus,
    solving,
    countdown,
    handleSolve,
  } as const;
}
