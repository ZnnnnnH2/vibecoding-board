import { useCallback, useEffect, useRef, useState, startTransition } from 'react'
import { api } from '../api'
import type { DashboardResponse, MetricsResponse, MetricsWindow, TokenUsageResponse } from '../types'
import { messagesByLocale } from '../i18n'

export function useDashboard(
  locale: keyof typeof messagesByLocale,
  pushToast: (tone: 'success' | 'error', text: string) => void
) {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [tokenUsage, setTokenUsage] = useState<TokenUsageResponse | null>(null)
  const [metricsWindow, setMetricsWindow] = useState<MetricsWindow>('24h')
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const activeRequestControllerRef = useRef<AbortController | null>(null)
  const metricsWindowRef = useRef(metricsWindow)
  metricsWindowRef.current = metricsWindow
  const initialLoadDone = useRef(false)
  const messages = messagesByLocale[locale]

  const cancelActiveRequest = useCallback(() => {
    activeRequestControllerRef.current?.abort()
    activeRequestControllerRef.current = null
    setLoading(false)
  }, [])

  const loadAdminData = useCallback(async () => {
    activeRequestControllerRef.current?.abort()
    activeRequestControllerRef.current = null
    const controller = new AbortController()
    activeRequestControllerRef.current = controller
    setLoading(true)

    try {
      const [dashboardResult, metricsResult, tokenUsageResult] = await Promise.allSettled([
        api.dashboard(controller.signal),
        api.metrics(metricsWindowRef.current, controller.signal),
        api.tokenUsage(controller.signal),
      ])

      if (dashboardResult.status === 'fulfilled') {
        startTransition(() => {
          setDashboard(dashboardResult.value)
        })
      } else if (
        !(dashboardResult.reason instanceof Error && dashboardResult.reason.name === 'AbortError')
      ) {
        pushToast(
          'error',
          dashboardResult.reason instanceof Error ? dashboardResult.reason.message : messages.app.loadFailed,
        )
      }

      if (metricsResult.status === 'fulfilled') {
        startTransition(() => {
          setMetrics(metricsResult.value)
        })
      } else if (
        !(metricsResult.reason instanceof Error && metricsResult.reason.name === 'AbortError')
      ) {
        pushToast(
          'error',
          metricsResult.reason instanceof Error ? metricsResult.reason.message : messages.app.metricsLoadFailed,
        )
      }

      if (tokenUsageResult.status === 'fulfilled') {
        startTransition(() => {
          setTokenUsage(tokenUsageResult.value)
        })
      }
    } finally {
      if (activeRequestControllerRef.current === controller) {
        activeRequestControllerRef.current = null
        setLoading(false)
      }
    }
    initialLoadDone.current = true
  }, [messages.app.loadFailed, messages.app.metricsLoadFailed, pushToast])

  useEffect(() => {
    void loadAdminData()
  }, [loadAdminData])

  useEffect(() => {
    if (!initialLoadDone.current) return
    const controller = new AbortController()
    api.metrics(metricsWindow, controller.signal)
      .then((result) => startTransition(() => setMetrics(result)))
      .catch((error) => {
        if (!(error instanceof Error && error.name === 'AbortError')) {
          pushToast('error', error instanceof Error ? error.message : messages.app.metricsLoadFailed)
        }
      })
    return () => controller.abort()
  }, [metricsWindow, pushToast, messages.app.metricsLoadFailed])

  useEffect(() => {
    return () => {
      activeRequestControllerRef.current?.abort()
      activeRequestControllerRef.current = null
    }
  }, [])

  async function runMutation<T extends { message: string; dashboard: DashboardResponse }>(
    actionKey: string,
    action: () => Promise<T>,
    onSuccess?: (response: T) => void,
  ): Promise<boolean> {
    cancelActiveRequest()
    setBusyAction(actionKey)
    try {
      const response = await action()
      startTransition(() => {
        setDashboard(response.dashboard)
      })
      onSuccess?.(response)
      pushToast('success', response.message)
      return true
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : messages.app.actionFailed)
      return false
    } finally {
      setBusyAction(null)
    }
  }

  return {
    dashboard,
    metrics,
    tokenUsage,
    metricsWindow,
    setMetricsWindow,
    busyAction,
    setBusyAction,
    loading,
    loadAdminData,
    runMutation,
    cancelActiveRequest,
    setDashboard
  }
}
