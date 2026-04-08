import { startTransition, useCallback, useEffect, useRef, useState } from 'react'
import {
  Cable,
  Globe2,
  LayoutDashboard,
  MoonStar,
  Plus,
  RefreshCw,
  ScrollText,
  SunMedium,
} from 'lucide-react'

import { api, setApiLocale } from './api'
import { formatTimestamp } from './format'
import { ConfirmDialog } from './components/ConfirmDialog'
import { OverviewView } from './components/OverviewView'
import { ProviderDrawer } from './components/ProviderDrawer'
import { ProvidersView } from './components/ProvidersView'
import { TrafficView } from './components/TrafficView'
import {
  I18nContext,
  loadLocalePreference,
  messagesByLocale,
  resolveLocale,
  saveLocalePreference,
} from './i18n'

import type {
  DashboardResponse,
  MetricsResponse,
  MetricsWindow,
  ProviderFormState,
  ProviderSummary,
} from './types'
import type { LocalePreference } from './i18n'

type AdminView = 'overview' | 'providers' | 'traffic'


const emptyForm: ProviderFormState = {
  name: '',
  baseUrl: '',
  apiKey: '',
  enabled: true,
  priority: '10',
  modelMode: 'explicit',
  modelText: '',
  healthcheckModel: '',
  timeoutSeconds: '60',
  maxFailures: '3',
  cooldownSeconds: '30',
}


function formFromProvider(provider: ProviderSummary): ProviderFormState {
  return {
    name: provider.name,
    baseUrl: provider.base_url,
    apiKey: '',
    enabled: provider.enabled,
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


export default function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [metricsWindow, setMetricsWindow] = useState<MetricsWindow>('24h')
  const [currentView, setCurrentView] = useState<AdminView>('overview')
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit' | null>(null)
  const [editingProvider, setEditingProvider] = useState<ProviderSummary | null>(null)
  const [form, setForm] = useState<ProviderFormState>(emptyForm)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [flash, setFlash] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)
  const [deletingProvider, setDeletingProvider] = useState<ProviderSummary | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>('light')
  const [localePreference, setLocalePreference] = useState<LocalePreference>(() => loadLocalePreference())
  const activeRequestControllerRef = useRef<AbortController | null>(null)
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
        : {
            title: messages.viewMeta.trafficTitle,
            description: messages.viewMeta.trafficDescription,
          }

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    saveLocalePreference(localePreference)
  }, [localePreference])

  useEffect(() => {
    setApiLocale(locale)
  }, [locale])

  function cancelActiveRequest() {
    activeRequestControllerRef.current?.abort()
    activeRequestControllerRef.current = null
    setLoading(false)
  }

  const loadAdminData = useCallback(async () => {
    activeRequestControllerRef.current?.abort()
    activeRequestControllerRef.current = null
    const controller = new AbortController()
    activeRequestControllerRef.current = controller
    setLoading(true)

    try {
      const [dashboardResult, metricsResult] = await Promise.allSettled([
        api.dashboard(controller.signal),
        api.metrics(metricsWindow, controller.signal),
      ])

      if (dashboardResult.status === 'fulfilled') {
        startTransition(() => {
          setDashboard(dashboardResult.value)
        })
      } else if (
        !(dashboardResult.reason instanceof Error && dashboardResult.reason.name === 'AbortError')
      ) {
        setFlash({
          tone: 'error',
          text: dashboardResult.reason instanceof Error ? dashboardResult.reason.message : messages.app.loadFailed,
        })
      }

      if (metricsResult.status === 'fulfilled') {
        startTransition(() => {
          setMetrics(metricsResult.value)
        })
      } else if (
        !(metricsResult.reason instanceof Error && metricsResult.reason.name === 'AbortError')
      ) {
        setFlash({
          tone: 'error',
          text: metricsResult.reason instanceof Error ? metricsResult.reason.message : messages.app.metricsLoadFailed,
        })
      }
    } finally {
      if (activeRequestControllerRef.current === controller) {
        activeRequestControllerRef.current = null
        setLoading(false)
      }
    }
  }, [messages.app.loadFailed, messages.app.metricsLoadFailed, metricsWindow])

  useEffect(() => {
    void loadAdminData()
  }, [loadAdminData])

  useEffect(() => {
    return () => {
      activeRequestControllerRef.current?.abort()
      activeRequestControllerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!flash) {
      return undefined
    }

    const timer = window.setTimeout(() => setFlash(null), 3500)
    return () => window.clearTimeout(timer)
  }, [flash])

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
      setFlash({ tone: 'success', text: response.message })
      return true
    } catch (error) {
      setFlash({
        tone: 'error',
        text: error instanceof Error ? error.message : messages.app.actionFailed,
      })
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

  async function handleHealthcheck(provider: ProviderSummary) {
    await runMutation(`health:${provider.name}`, () => api.healthcheckProvider(provider.name))
  }

  async function handlePrioritySave(provider: ProviderSummary, priority: number): Promise<boolean> {
    return runMutation(`priority:${provider.name}`, () => api.updateProviderPriority(provider.name, priority))
  }

  async function handleDeleteConfirm() {
    if (!deletingProvider) {
      return
    }

    const provider = deletingProvider
    const success = await runMutation(`delete:${provider.name}`, () => api.deleteProvider(provider.name))
    if (success) {
      setDeletingProvider(null)
    }
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
        </nav>

        <div className="sidebar-status">
          <div className="sidebar-status-card">
            <span className="surface-label">{messages.app.sidebarPrimaryProvider}</span>
            <strong>{dashboard?.primary_provider ?? messages.app.waitingForRuntime}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="surface-label">{messages.app.sidebarLastReload}</span>
            <strong>{dashboard ? formatTimestamp(dashboard.reloaded_at) : messages.app.loading}</strong>
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
              <label className="select-field locale-select">
                <Globe2 size={16} />
                <span className="surface-label">{messages.locale.label}</span>
                <select
                  value={localePreference}
                  onChange={(event) => setLocalePreference(event.target.value as LocalePreference)}
                  aria-label={messages.locale.label}
                >
                  <option value="auto">{messages.locale.auto}</option>
                  <option value="zh-CN">{messages.locale.chinese}</option>
                  <option value="en">{messages.locale.english}</option>
                </select>
              </label>

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
                onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
              >
                {theme === 'dark' ? <SunMedium size={16} /> : <MoonStar size={16} />}
                {theme === 'dark' ? messages.app.lightMode : messages.app.darkMode}
              </button>
            </div>
          </div>
        </header>

        {flash ? <div className={`flash-banner flash-banner-${flash.tone}`}>{flash.text}</div> : null}

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
              onDelete={(provider) => setDeletingProvider(provider)}
              onPrioritySave={handlePrioritySave}
            />
          ) : (
            <TrafficView requests={dashboard.recent_requests} />
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

      <ConfirmDialog
        open={deletingProvider !== null}
        title={deletingProvider ? messages.confirm.deleteTitle(deletingProvider.name) : messages.confirm.deleteProvider}
        description={deletingProvider ? messages.confirm.deleteDescription : ''}
        busy={busyAction === `delete:${deletingProvider?.name ?? ''}`}
        onCancel={() => setDeletingProvider(null)}
        onConfirm={() => {
          void handleDeleteConfirm()
        }}
      />
      </div>
    </I18nContext.Provider>
  )
}
