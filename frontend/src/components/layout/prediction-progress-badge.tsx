'use client'

import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'

type ProgressData =
  | { is_running: false }
  | {
      is_running: true
      total: number
      scored: number
      percentage: number
      eta_seconds: number
    }

type CompletedRun = { total: number }

export function PredictionProgressBadge() {
  const [progress, setProgress] = useState<ProgressData>({ is_running: false })
  const [completed, setCompleted] = useState<CompletedRun | null>(null)

  useEffect(() => {
    let mounted = true
    const abortController = new AbortController()

    const fetchProgress = async () => {
      try {
        const response = await fetch('/api/ml/predictions/progress', {
          signal: abortController.signal,
        })
        if (!response.ok) return
        const data = (await response.json()) as ProgressData
        if (!mounted) return

        // Keep a snapshot of the total from the most recent running tick
        // so the badge can show "N/N (100%)" after scoring ends instead of
        // vanishing the moment is_running flips to false.
        if (data.is_running) {
          setCompleted({ total: data.total })
        }

        setProgress(data)
      } catch (error) {
        if (error instanceof Error && error.name !== 'AbortError') {
          // Ignore abort errors from cleanup
        }
      }
    }

    fetchProgress()
    const interval = setInterval(fetchProgress, 3000)

    return () => {
      mounted = false
      clearInterval(interval)
      abortController.abort()
    }
  }, [])

  const formatEta = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s`
    }
    const minutes = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${minutes}m ${secs}s`
  }

  if (progress.is_running) {
    const eta = formatEta(progress.eta_seconds)
    return (
      <Badge
        variant="secondary"
        className="animate-pulse bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"
      >
        <span className="text-sm font-medium">
          {progress.scored}/{progress.total} ({progress.percentage}%) • ETA: {eta}
        </span>
      </Badge>
    )
  }

  // Finished: show 100% persistently until the next run starts.
  if (completed && completed.total > 0) {
    return (
      <Badge
        variant="secondary"
        className="bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
      >
        <span className="text-sm font-medium">
          {completed.total}/{completed.total} (100%)
        </span>
      </Badge>
    )
  }

  return null
}
