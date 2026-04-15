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

export function PredictionProgressBadge() {
  const [progress, setProgress] = useState<ProgressData>({ is_running: false })

  useEffect(() => {
    let mounted = true
    let abortController = new AbortController()

    const fetchProgress = async () => {
      try {
        const response = await fetch('/api/ml/predictions/progress', {
          signal: abortController.signal,
        })
        if (!response.ok) return
        const data = (await response.json()) as ProgressData
        if (mounted) {
          setProgress(data)
        }
      } catch (error) {
        // Silent fail on network errors (tab may be hidden, network may be down)
        if (error instanceof Error && error.name !== 'AbortError') {
          // Ignore abort errors from cleanup
        }
      }
    }

    // Fetch immediately
    fetchProgress()

    // Poll every 3 seconds
    const interval = setInterval(fetchProgress, 3000)

    return () => {
      mounted = false
      clearInterval(interval)
      abortController.abort()
    }
  }, [])

  if (!progress.is_running) {
    return null
  }

  const formatEta = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s`
    }
    const minutes = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${minutes}m ${secs}s`
  }

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
