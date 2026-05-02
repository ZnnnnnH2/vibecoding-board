import { useEffect, useState } from 'react'
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

import { setApiLocale, api } from './api'
import { formatTimestamp } from './format'
import { AppLogo } from './components/AppLogo'
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
  HealthcheckSettingsFormState,
  HealthcheckSummary,
  ProviderSummary,
  ResponsesWebSocketSettingsFormState,
  RetryPolicyFormState,
  TrafficPreset,
  DashboardResponse,
} from './types'
import type { LocalePreference } from './i18n'
import type { ResolvedTheme, ThemePreference } from './theme'

import { useToasts } from './hooks/useToasts'
import { useDashboard } from './hooks/useDashboard'
import { useProviderManager } from './hooks/useProviderManager'

type AdminView = 'overview' | 'providers' | 'traffic' | 'settings'

type DialogState =
  | { kind: 'confirm-delete'; provider: ProviderSummary }
  | { kind: 'healthcheck-result'; providerName: string; healthcheck: HealthcheckSummary }
  | null

const emptyHealthcheck: HealthcheckSummary = {
  checked_at: null,
  ok: null,
  status_code: null,
  latency_ms: null,
  stream: null,
  model: null,
  error: null,
}

const defaultHealthcheckModel = 'gpt-5.4'
const defaultRetryableStatusCodes = [429, 500, 502, 503, 504]
const defaultProviderFailureStatusCodes = [401, 403]

function formatStatusCodes(value: unknown, fallback: number[]): string {
  return (Array.isArray(value) ? value : fallback).join(', ')
}

function createRetryPolicyForm(dashboard: DashboardResponse | null): RetryPolicyFormState {
  return {
    retryableStatusCodes: formatStatusCodes(
      dashboard?.retry_policy?.retryable_status_codes,
      defaultRetryableStatusCodes,
    ),
    providerFailureStatusCodes: formatStatusCodes(
      dashboard?.retry_policy?.provider_failure_status_codes,
      defaultProviderFailureStatusCodes,
    ),
    sameProviderRetryCount: String(dashboard?.retry_policy?.same_provider_retry_count ?? 0),
    retryIntervalMs: String(dashboard?.retry_policy?.retry_interval_ms ?? 0),
    retryExponentialBackoff: dashboard?.retry_policy?.retry_exponential_backoff ?? false,
  }
}

function createHealthcheckSettingsForm(dashboard: DashboardResponse | null): HealthcheckSettingsFormState {
  return {
    stream: dashboard?.healthcheck?.stream ?? false,
    model: dashboard?.healthcheck?.model ?? defaultHealthcheckModel,
  }
}

function createResponsesWebSocketSettingsForm(
  dashboard: DashboardResponse | null,
): ResponsesWebSocketSettingsFormState {
  return {
    enabled: dashboard?.responses_websocket?.enabled ?? false,
  }
}

function retryPolicyFormsEqual(
  left: RetryPolicyFormState,
  right: RetryPolicyFormState,
): boolean {
  return (
    left.retryableStatusCodes === right.retryableStatusCodes &&
    left.providerFailureStatusCodes === right.providerFailureStatusCodes &&
    left.sameProviderRetryCount === right.sameProviderRetryCount &&
    left.retryIntervalMs === right.retryIntervalMs &&
    left.retryExponentialBackoff === right.retryExponentialBackoff
  )
}

function healthcheckSettingsFormsEqual(
  left: HealthcheckSettingsFormState,
  right: HealthcheckSettingsFormState,
): boolean {
  return left.stream === right.stream && left.model === right.model
}

function responsesWebSocketSettingsFormsEqual(
  left: ResponsesWebSocketSettingsFormState,
  right: ResponsesWebSocketSettingsFormState,
): boolean {
  return left.enabled === right.enabled
}

export default function App() {
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => loadThemePreference())
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => getSystemTheme())
  const [localePreference, setLocalePreference] = useState<LocalePreference>(() => loadLocalePreference())

  const theme = resolveTheme(themePreference, systemTheme)
  const locale = resolveLocale(localePreference)
  const messages = messagesByLocale[locale]

  const { toasts, pushToast, dismissToast } = useToasts()
  const {
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
  } = useDashboard(locale, pushToast)

  const [currentView, setCurrentView] = useState<AdminView>('overview')
  const [trafficPreset, setTrafficPreset] = useState<TrafficPreset | null>(null)
  
  const {
    drawerMode,
    form,
    setForm,
    providerDrawerBusy,
    openCreateDrawer,
    openEditDrawer,
    closeDrawer,
    handleSubmit,
    handleProviderAutoSave,
    handlePromote,
    handleToggle,
    handleToggleAlwaysAlive,
    handlePrioritySave
  } = useProviderManager(dashboard, runMutation, setCurrentView, busyAction)

  const [retryPolicyForm, setRetryPolicyForm] = useState<RetryPolicyFormState>(() => createRetryPolicyForm(null))
  const [healthcheckForm, setHealthcheckForm] = useState<HealthcheckSettingsFormState>(() =>
    createHealthcheckSettingsForm(null),
  )
  const [responsesWebSocketForm, setResponsesWebSocketForm] =
    useState<ResponsesWebSocketSettingsFormState>(() => createResponsesWebSocketSettingsForm(null))

  const [showFloatingRefresh, setShowFloatingRefresh] = useState(false)
  const [dialog, setDialog] = useState<DialogState>(null)

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

  useEffect(() => {
    const handleScroll = () => {
      setShowFloatingRefresh(window.scrollY > 240)
    }

    handleScroll()
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

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
    setResponsesWebSocketForm(createResponsesWebSocketSettingsForm(dashboard))
  }, [dashboard])

  const openHealthcheckDialog = (providerName: string, healthcheck: HealthcheckSummary) => {
    setDialog({
      kind: 'healthcheck-result',
      providerName,
      healthcheck,
    })
  }

  async function handleHealthcheck(provider: ProviderSummary) {
    cancelActiveRequest()
    setBusyAction(`health:${provider.name}`)
    try {
      const response = await api.healthcheckProvider(provider.name)
      setDashboard(response.dashboard)
      const updatedProvider = response.dashboard.providers.find((item) => item.name === provider.name)
      openHealthcheckDialog(provider.name, updatedProvider?.healthcheck ?? provider.healthcheck)
    } catch (error) {
      openHealthcheckDialog(provider.name, {
        ...emptyHealthcheck,
        ok: false,
        stream: dashboard?.healthcheck.stream ?? null,
        model: dashboard?.healthcheck.model ?? null,
        error: error instanceof Error ? error.message : messages.app.actionFailed,
      })
    } finally {
      setBusyAction(null)
    }
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

  async function handleRetryPolicySubmit(nextForm: RetryPolicyFormState) {
    if (busyAction !== null || !dashboard) {
      return
    }

    setRetryPolicyForm(nextForm)
    if (retryPolicyFormsEqual(nextForm, createRetryPolicyForm(dashboard))) {
      return
    }

    await runMutation('retry-policy', () => api.updateRetryPolicy(nextForm))
  }

  async function handleHealthcheckSettingsSubmit(nextForm: HealthcheckSettingsFormState) {
    if (busyAction !== null || !dashboard) {
      return
    }

    setHealthcheckForm(nextForm)
    if (healthcheckSettingsFormsEqual(nextForm, createHealthcheckSettingsForm(dashboard))) {
      return
    }

    await runMutation('healthcheck-settings', () => api.updateHealthcheckSettings(nextForm))
  }

  async function handleResponsesWebSocketSettingsSubmit(
    nextForm: ResponsesWebSocketSettingsFormState,
  ) {
    if (busyAction !== null || !dashboard) {
      return
    }

    setResponsesWebSocketForm(nextForm)
    if (
      responsesWebSocketSettingsFormsEqual(
        nextForm,
        createResponsesWebSocketSettingsForm(dashboard),
      )
    ) {
      return
    }

    await runMutation(
      'responses-websocket-settings',
      () => api.updateResponsesWebSocketSettings(nextForm),
    )
  }

  function navigateAdmin(view: AdminView, nextTrafficPreset?: TrafficPreset) {
    if (view === 'traffic') {
      setTrafficPreset(nextTrafficPreset ?? null)
    }
    setCurrentView(view)
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
          <div className="brand-lockup">
            <AppLogo className="brand-mark" title={messages.app.brand} />
            <div className="brand-copy">
              <span className="eyebrow">{messages.app.brand}</span>
              <h2>{messages.app.adminConsole}</h2>
            </div>
          </div>
          <p>{messages.app.sidebarCopy}</p>
        </div>

        <nav className="sidebar-nav">
          <button
            type="button"
            className={`nav-item${currentView === 'overview' ? ' nav-item-active' : ''}`}
            onClick={() => navigateAdmin('overview')}
          >
            <LayoutDashboard size={18} />
            <span>{messages.app.navOverview}</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'providers' ? ' nav-item-active' : ''}`}
            onClick={() => navigateAdmin('providers')}
          >
            <Cable size={18} />
            <span>{messages.app.navProviders}</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'traffic' ? ' nav-item-active' : ''}`}
            onClick={() => navigateAdmin('traffic')}
          >
            <ScrollText size={18} />
            <span>{messages.app.navTraffic}</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'settings' ? ' nav-item-active' : ''}`}
            onClick={() => navigateAdmin('settings')}
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
              onNavigate={(view, preset) => navigateAdmin(view, preset)}
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
            <TrafficView requests={dashboard.recent_requests} preset={trafficPreset} />
          ) : (
            <SettingsView
              settingsBusy={busyAction !== null}
              retryPolicyForm={retryPolicyForm}
              retryPolicyBusy={busyAction === 'retry-policy'}
              onRetryPolicyChange={setRetryPolicyForm}
              onRetryPolicySubmit={(nextForm) => {
                void handleRetryPolicySubmit(nextForm)
              }}
              healthcheckForm={healthcheckForm}
              healthcheckBusy={busyAction === 'healthcheck-settings'}
              onHealthcheckChange={setHealthcheckForm}
              onHealthcheckSubmit={(nextForm) => {
                void handleHealthcheckSettingsSubmit(nextForm)
              }}
              responsesWebSocketForm={responsesWebSocketForm}
              responsesWebSocketBusy={busyAction === 'responses-websocket-settings'}
              onResponsesWebSocketChange={setResponsesWebSocketForm}
              onResponsesWebSocketSubmit={(nextForm) => {
                void handleResponsesWebSocketSettingsSubmit(nextForm)
              }}
            />
          )}
        </main>
      </div>

      {showFloatingRefresh ? (
        <button
          type="button"
          className="floating-refresh-button"
          onClick={() => {
            void loadAdminData()
          }}
          disabled={loading}
          aria-label={loading ? messages.app.refreshing : messages.app.refresh}
        >
          <RefreshCw size={18} className={loading ? 'spin-icon' : ''} />
          <span>{loading ? messages.app.refreshing : messages.app.refresh}</span>
        </button>
      ) : null}

      <ProviderDrawer
        open={drawerMode !== null}
        mode={drawerMode ?? 'create'}
        busy={providerDrawerBusy}
        form={form}
        onClose={closeDrawer}
        onChange={setForm}
        onSubmit={(nextForm) => {
          void handleSubmit(nextForm)
        }}
        onAutoSave={(nextForm) => {
          void handleProviderAutoSave(nextForm)
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