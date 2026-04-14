import { startTransition, useCallback, useEffect, useRef, useState } from 'react'
import {
  Cable,
  Globe2,
  LayoutDashboard,
  MoonStar,
  Plus,
  RefreshCw,
  SlidersHorizontal,
  ScrollText,
  SunMedium,
} from 'lucide-react'

import { api, setApiLocale } from './api'
import { formatTimestamp } from './format'
import { ConfirmDialog } from './components/ConfirmDialog'
import { OverviewView } from './components/OverviewView'
import { ProviderDrawer } from './components/ProviderDrawer'
import { ProvidersView } from './components/ProvidersView'
import { ResultDialog } from './components/ResultDialog'
import { SettingsView } from './components/SettingsView'
import { ToastStack } from './components/ToastStack'
import { TrafficView } from './components/TrafficView'
import {
  I18nContext,
  loadLocalePreference,
  messagesByLocale,
  resolveLocale,
  saveLocalePreference,
} from './i18n'
import {
  getSystemTheme,
  loadThemePreference,
  resolveTheme,
  saveThemePreference,
} from './theme'
import { DropdownSelect } from './components/DropdownSelect'

import type {
  DashboardResponse,
  HealthcheckSettingsFormState,
  HealthcheckSummary,
  MetricsResponse,
  MetricsWindow,
  ProviderFormState,
  ProviderSummary,
  RetryPolicyFormState,
  TokenUsageResponse,
} from './types'
import type { LocalePreference } from './i18n'
import type { ResolvedTheme, ThemePreference } from './theme'

type AdminView = 'overview' | 'providers' | 'traffic' | 'settings'

type ToastNotification = {
  id: number
  tone: 'success' | 'error'
  text: string
}

type DialogState =
  | { kind: 'confirm-delete'; provider: ProviderSummary }
  | { kind: 'healthcheck-result'; providerName: string; healthcheck: HealthcheckSummary }
  | null


const emptyForm: ProviderFormState = {
  name: '',
  baseUrl: '',
  apiKey: '',
  enabled: true,
  alwaysAlive: false,
  priority: '10',
  modelMode: 'explicit',
  modelText: '',
  healthcheckModel: '',
  timeoutSeconds: '60',
  maxFailures: '3',
  cooldownSeconds: '30',
}

const emptyHealthcheck: HealthcheckSummary = {
  checked_at: null,
  ok: null,
  status_code: null,
  latency_ms: null,
  stream: null,
  model: null,
  error: null,
}


function formFromProvider(provider: ProviderSummary): ProviderFormState {
  return {
    name: provider.name,
    baseUrl: provider.base_url,
    apiKey: '',
    enabled: provider.enabled,
    alwaysAlive: provider.always_alive,
    priority: String(provider.priority),
    modelMode: provider.supports_all_models ? 'all' : 'explicit',
    modelText: provider.supports_all_models ? '' : provider.models.join('\n'),
    healthcheckModel: provider.healthcheck_model ?? '',
    timeoutSeconds: String(provider.timeout_seconds),
    maxFailures: String(provider.max_failures),
    cooldownSeconds: String(provider.cooldown_seconds),
  }
}


function createProviderForm(dashboard: DashboardResponse | null): ProviderFormState {
  return {
    ...emptyForm,
    priority: String(
      dashboard?.providers.length
        ? Math.max(...dashboard.providers.map((provider) => provider.priority)) + 10
        : 10,
    ),
  }
}


function createRetryPolicyForm(dashboard: DashboardResponse | null): RetryPolicyFormState {
  return {
    retryableStatusCodes: dashboard?.retry_policy.retryable_status_codes.join(', ') ?? '429, 500, 502, 503, 504',
    sameProviderRetryCount: String(dashboard?.retry_policy.same_provider_retry_count ?? 0),
    retryIntervalMs: String(dashboard?.retry_policy.retry_interval_ms ?? 0),
  }
}


function createHealthcheckSettingsForm(dashboard: DashboardResponse | null): HealthcheckSettingsFormState {
  return {
    stream: dashboard?.healthcheck.stream ?? false,
  }
}


export default function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [tokenUsage, setTokenUsage] = useState<TokenUsageResponse | null>(null)
  const [metricsWindow, setMetricsWindow] = useState<MetricsWindow>('24h')
  const [currentView, setCurrentView] = useState<AdminView>('overview')
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit' | null>(null)
  const [editingProvider, setEditingProvider] = useState<ProviderSummary | null>(null)
  const [form, setForm] = useState<ProviderFormState>(emptyForm)
  const [retryPolicyForm, setRetryPolicyForm] = useState<RetryPolicyFormState>(() => createRetryPolicyForm(null))
  const [healthcheckForm, setHealthcheckForm] = useState<HealthcheckSettingsFormState>(() =>
    createHealthcheckSettingsForm(null),
  )
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [toasts, setToasts] = useState<ToastNotification[]>([])
  const [dialog, setDialog] = useState<DialogState>(null)
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => loadThemePreference())
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => getSystemTheme())
  const [localePreference, setLocalePreference] = useState<LocalePreference>(() => loadLocalePreference())
  const activeRequestControllerRef = useRef<AbortController | null>(null)
  const toastIdRef = useRef(0)
  const toastTimerIds = useRef(new Set<number>())
  const metricsWindowRef = useRef(metricsWindow)
  metricsWindowRef.current = metricsWindow
  const initialLoadDone = useRef(false)
  const theme = resolveTheme(themePreference, systemTheme)
  const locale = resolveLocale(localePreference)
  const messages = messagesByLocale[locale]

  const meta =
    currentView === 'overview'
      ? {
          title: messages.viewMeta.overviewTitle,
          description: messages.viewMeta.overviewDescription,
        }
        : currentView === 'providers'
        ? {
            title: messages.viewMeta.providersTitle,
            description: messages.viewMeta.providersDescription,
          }
        : currentView === 'traffic'
        ? {
            title: messages.viewMeta.trafficTitle,
            description: messages.viewMeta.trafficDescription,
          }
        : {
            title: messages.viewMeta.settingsTitle,
            description: messages.viewMeta.settingsDescription,
          }

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    saveThemePreference(themePreference)
  }, [themePreference])

  useEffect(() => {
    saveLocalePreference(localePreference)
  }, [localePreference])

  useEffect(() => {
    setApiLocale(locale)
  }, [locale])

  const cancelActiveRequest = useCallback(() => {
    activeRequestControllerRef.current?.abort()
    activeRequestControllerRef.current = null
    setLoading(false)
  }, [])

  const pushToast = useCallback((tone: ToastNotification['tone'], text: string) => {
    toastIdRef.current += 1
    setToasts((current) => [...current, { id: toastIdRef.current, tone, text }])
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const openHealthcheckDialog = useCallback((providerName: string, healthcheck: HealthcheckSummary) => {
    setDialog({
      kind: 'healthcheck-result',
      providerName,
      healthcheck,
    })
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

  useEffect(() => {
    for (const toast of toasts) {
      if (toastTimerIds.current.has(toast.id)) continue
      toastTimerIds.current.add(toast.id)
      window.setTimeout(() => {
        toastTimerIds.current.delete(toast.id)
        setToasts((current) => current.filter((item) => item.id !== toast.id))
      }, 3500)
    }
  }, [toasts])

  useEffect(() => {
    if (themePreference !== 'auto' || typeof window === 'undefined') {
      return undefined
    }

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? 'dark' : 'light')
    }

    setSystemTheme(mediaQuery.matches ? 'dark' : 'light')

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }

    mediaQuery.addListener(handleChange)
    return () => mediaQuery.removeListener(handleChange)
  }, [themePreference])

  useEffect(() => {
    if (!dashboard) {
      return
    }
    setRetryPolicyForm(createRetryPolicyForm(dashboard))
    setHealthcheckForm(createHealthcheckSettingsForm(dashboard))
  }, [dashboard])

  async function runMutation(
    actionKey: string,
    action: () => Promise<{ message: string; dashboard: DashboardResponse }>,
  ): Promise<boolean> {
    cancelActiveRequest()
    setBusyAction(actionKey)
    try {
      const response = await action()
      startTransition(() => {
        setDashboard(response.dashboard)
      })
      pushToast('success', response.message)
      return true
    } catch (error) {
      pushToast('error', error instanceof Error ? error.message : messages.app.actionFailed)
      return false
    } finally {
      setBusyAction(null)
    }
  }

  function openCreateDrawer() {
    setCurrentView('providers')
    setEditingProvider(null)
    setForm(createProviderForm(dashboard))
    setDrawerMode('create')
  }

  function openEditDrawer(provider: ProviderSummary) {
    setCurrentView('providers')
    setEditingProvider(provider)
    setForm(formFromProvider(provider))
    setDrawerMode('edit')
  }

  function closeDrawer() {
    if (busyAction === 'submit') {
      return
    }
    setDrawerMode(null)
    setEditingProvider(null)
    setForm(createProviderForm(dashboard))
  }

  async function handleSubmit() {
    if (!drawerMode) {
      return
    }

    const success = await runMutation('submit', async () => {
      if (drawerMode === 'create') {
        return api.createProvider(form)
      }
      return api.updateProvider(editingProvider!.name, form)
    })

    if (success) {
      closeDrawer()
    }
  }

  async function handlePromote(provider: ProviderSummary) {
    await runMutation(`promote:${provider.name}`, () => api.promoteProvider(provider.name))
  }

  async function handleToggle(provider: ProviderSummary) {
    await runMutation(`toggle:${provider.name}`, () => api.toggleProvider(provider.name))
  }

  async function handleToggleAlwaysAlive(provider: ProviderSummary) {
    await runMutation(`always-alive:${provider.name}`, () => api.toggleProviderAlwaysAlive(provider.name))
  }

  async function handleHealthcheck(provider: ProviderSummary) {
    cancelActiveRequest()
    setBusyAction(`health:${provider.name}`)
    try {
      const response = await api.healthcheckProvider(provider.name)
      startTransition(() => {
        setDashboard(response.dashboard)
      })
      const updatedProvider = response.dashboard.providers.find((item) => item.name === provider.name)
      openHealthcheckDialog(provider.name, updatedProvider?.healthcheck ?? provider.healthcheck)
    } catch (error) {
      openHealthcheckDialog(provider.name, {
        ...emptyHealthcheck,
        ok: false,
        stream: dashboard?.healthcheck.stream ?? null,
        error: error instanceof Error ? error.message : messages.app.actionFailed,
      })
    } finally {
      setBusyAction(null)
    }
  }

  async function handlePrioritySave(provider: ProviderSummary, priority: number): Promise<boolean> {
    return runMutation(`priority:${provider.name}`, () => api.updateProviderPriority(provider.name, priority))
  }

  async function handleDeleteConfirm() {
    if (dialog?.kind !== 'confirm-delete') {
      return
    }

    const provider = dialog.provider
    const success = await runMutation(`delete:${provider.name}`, () => api.deleteProvider(provider.name))
    if (success) {
      setDialog(null)
    }
  }

  async function handleRetryPolicySubmit() {
    await runMutation('retry-policy', () => api.updateRetryPolicy(retryPolicyForm))
  }

  async function handleHealthcheckSettingsSubmit() {
    await runMutation('healthcheck-settings', () => api.updateHealthcheckSettings(healthcheckForm))
  }

  const proxyBase =
    dashboard === null
      ? 'http://127.0.0.1:9000/v1'
      : `http://${dashboard.listen_host}:${dashboard.listen_port}/v1`

  return (
    <I18nContext.Provider
      value={{
        locale,
        localePreference,
        setLocalePreference,
        messages,
      }}
    >
      <div className="admin-shell">
      <aside className="shell-sidebar">
        <div className="sidebar-brand">
          <span className="eyebrow">{messages.app.brand}</span>
          <h2>{messages.app.adminConsole}</h2>
          <p>{messages.app.sidebarCopy}</p>
        </div>

        <nav className="sidebar-nav">
          <button
            type="button"
            className={`nav-item${currentView === 'overview' ? ' nav-item-active' : ''}`}
            onClick={() => setCurrentView('overview')}
          >
            <LayoutDashboard size={18} />
            <span>{messages.app.navOverview}</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'providers' ? ' nav-item-active' : ''}`}
            onClick={() => setCurrentView('providers')}
          >
            <Cable size={18} />
            <span>{messages.app.navProviders}</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'traffic' ? ' nav-item-active' : ''}`}
            onClick={() => setCurrentView('traffic')}
          >
            <ScrollText size={18} />
            <span>{messages.app.navTraffic}</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'settings' ? ' nav-item-active' : ''}`}
            onClick={() => setCurrentView('settings')}
          >
            <SlidersHorizontal size={18} />
            <span>{messages.app.navSettings}</span>
          </button>
        </nav>

        <div className="sidebar-status">
          <div className="sidebar-status-card">
            <span className="surface-label">{messages.app.sidebarPrimaryProvider}</span>
            <strong>{dashboard?.primary_provider ?? messages.app.waitingForRuntime}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="surface-label">{messages.app.sidebarLastReload}</span>
            <strong>{dashboard ? formatTimestamp(dashboard.reloaded_at, locale) : messages.app.loading}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="surface-label">{messages.app.sidebarSyncState}</span>
            <strong>{loading ? messages.app.refreshingDashboard : messages.app.dashboardInSync}</strong>
          </div>
        </div>
      </aside>

      <div className="shell-main">
        <header className="shell-header">
          <div className="header-copy">
            <span className="eyebrow">{messages.app.adminEyebrow}</span>
            <h1>{meta.title}</h1>
            <p>{meta.description}</p>
          </div>

          <div className="header-controls">
            <div className="header-meta">
              <div className="meta-chip">
                <span className="surface-label">{messages.app.proxyEndpoint}</span>
                <strong>{proxyBase}</strong>
              </div>
              <div className="meta-chip">
                <span className="surface-label">{messages.app.configPath}</span>
                <strong>{dashboard?.config_path ?? messages.app.loading}</strong>
              </div>
            </div>

            <div className="header-actions">
              <DropdownSelect
                value={localePreference}
                onChange={(val) => setLocalePreference(val as LocalePreference)}
                options={[
                  { value: 'auto', label: messages.locale.auto },
                  { value: 'zh-CN', label: messages.locale.chinese },
                  { value: 'en', label: messages.locale.english },
                ]}
                icon={<Globe2 size={16} />}
                prefixLabel={messages.locale.label}
                ariaLabel={messages.locale.label}
              />

              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  void loadAdminData()
                }}
                disabled={loading}
              >
                <RefreshCw size={16} className={loading ? 'spin-icon' : ''} />
                {loading ? messages.app.refreshing : messages.app.refresh}
              </button>

              <button type="button" className="accent-button" onClick={openCreateDrawer}>
                <Plus size={16} />
                {messages.app.addProvider}
              </button>

              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setThemePreference(theme === 'dark' ? 'light' : 'dark')
                }}
              >
                {theme === 'dark' ? <SunMedium size={16} /> : <MoonStar size={16} />}
                {theme === 'dark' ? messages.app.lightMode : messages.app.darkMode}
              </button>
            </div>
          </div>
        </header>

        <main className="shell-content">
          {!dashboard ? (
            <section className="surface-card loading-state">
              <span className="eyebrow">{messages.app.runtime}</span>
              <h2>{loading ? messages.app.loadingDashboard : messages.app.dashboardUnavailable}</h2>
              <p>
                {loading
                  ? messages.app.collectingSnapshot
                  : messages.app.retryAfterBackend}
              </p>
              {!loading ? (
                <button
                  type="button"
                  className="accent-button"
                  onClick={() => {
                    void loadAdminData()
                  }}
                >
                  {messages.app.retry}
                </button>
              ) : null}
            </section>
          ) : currentView === 'overview' ? (
            <OverviewView
              dashboard={dashboard}
              metrics={metrics}
              tokenUsage={tokenUsage}
              metricsWindow={metricsWindow}
              proxyBase={proxyBase}
              loading={loading}
              onMetricsWindowChange={(window) => setMetricsWindow(window)}
              onNavigate={(view) => setCurrentView(view)}
            />
          ) : currentView === 'providers' ? (
            <ProvidersView
              dashboard={dashboard}
              busyAction={busyAction}
              onCreate={openCreateDrawer}
              onEdit={openEditDrawer}
              onHealthcheck={handleHealthcheck}
              onPromote={handlePromote}
              onToggle={handleToggle}
              onToggleAlwaysAlive={handleToggleAlwaysAlive}
              onDelete={(provider) => setDialog({ kind: 'confirm-delete', provider })}
              onPrioritySave={handlePrioritySave}
            />
          ) : currentView === 'traffic' ? (
            <TrafficView requests={dashboard.recent_requests} />
          ) : (
            <SettingsView
              retryPolicyForm={retryPolicyForm}
              retryPolicyBusy={busyAction === 'retry-policy'}
              onRetryPolicyChange={setRetryPolicyForm}
              onRetryPolicySubmit={() => {
                void handleRetryPolicySubmit()
              }}
              healthcheckForm={healthcheckForm}
              healthcheckBusy={busyAction === 'healthcheck-settings'}
              onHealthcheckChange={setHealthcheckForm}
              onHealthcheckSubmit={() => {
                void handleHealthcheckSettingsSubmit()
              }}
            />
          )}
        </main>
      </div>

      <ProviderDrawer
        open={drawerMode !== null}
        mode={drawerMode ?? 'create'}
        busy={busyAction === 'submit'}
        form={form}
        onClose={closeDrawer}
        onChange={setForm}
        onSubmit={() => {
          void handleSubmit()
        }}
      />

      <ResultDialog
        open={dialog?.kind === 'healthcheck-result'}
        providerName={dialog?.kind === 'healthcheck-result' ? dialog.providerName : ''}
        healthcheck={dialog?.kind === 'healthcheck-result' ? dialog.healthcheck : emptyHealthcheck}
        onClose={() => setDialog(null)}
      />

      <ConfirmDialog
        open={dialog?.kind === 'confirm-delete'}
        title={dialog?.kind === 'confirm-delete' ? messages.confirm.deleteTitle(dialog.provider.name) : messages.confirm.deleteProvider}
        description={dialog?.kind === 'confirm-delete' ? messages.confirm.deleteDescription : ''}
        busy={busyAction === `delete:${dialog?.kind === 'confirm-delete' ? dialog.provider.name : ''}`}
        onCancel={() => setDialog(null)}
        onConfirm={() => {
          void handleDeleteConfirm()
        }}
      />

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
      </div>
    </I18nContext.Provider>
  )
}
