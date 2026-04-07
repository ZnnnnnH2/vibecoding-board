import { startTransition, useCallback, useEffect, useRef, useState } from 'react'
import {
  Cable,
  LayoutDashboard,
  MoonStar,
  Plus,
  RefreshCw,
  ScrollText,
  SunMedium,
} from 'lucide-react'

import { api } from './api'
import { formatTimestamp } from './format'
import { ConfirmDialog } from './components/ConfirmDialog'
import { OverviewView } from './components/OverviewView'
import { ProviderDrawer } from './components/ProviderDrawer'
import { ProvidersView } from './components/ProvidersView'
import { TrafficView } from './components/TrafficView'

import type { DashboardResponse, ProviderFormState, ProviderSummary } from './types'


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

const viewMeta: Record<AdminView, { title: string; description: string }> = {
  overview: {
    title: 'Overview',
    description: 'Global runtime status, provider health, and recent traffic signals.',
  },
  providers: {
    title: 'Providers',
    description: 'Operational workspace for routing priority, health checks, and hot updates.',
  },
  traffic: {
    title: 'Traffic',
    description: 'Inspect recent request routing outcomes, failover attempts, and timing data.',
  },
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
  const [currentView, setCurrentView] = useState<AdminView>('overview')
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit' | null>(null)
  const [editingProvider, setEditingProvider] = useState<ProviderSummary | null>(null)
  const [form, setForm] = useState<ProviderFormState>(emptyForm)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [flash, setFlash] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)
  const [deletingProvider, setDeletingProvider] = useState<ProviderSummary | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>('light')
  const activeRequestControllerRef = useRef<AbortController | null>(null)

  const meta = viewMeta[currentView]

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  function cancelActiveRequest() {
    activeRequestControllerRef.current?.abort()
    activeRequestControllerRef.current = null
    setLoading(false)
  }

  const loadDashboard = useCallback(async () => {
    cancelActiveRequest()
    const controller = new AbortController()
    activeRequestControllerRef.current = controller
    setLoading(true)

    try {
      const nextDashboard = await api.dashboard(controller.signal)
      startTransition(() => {
        setDashboard(nextDashboard)
      })
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return
      }
      setFlash({
        tone: 'error',
        text: error instanceof Error ? error.message : 'Failed to load dashboard.',
      })
    } finally {
      if (activeRequestControllerRef.current === controller) {
        activeRequestControllerRef.current = null
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard])

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
        text: error instanceof Error ? error.message : 'Action failed.',
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
    <div className="admin-shell">
      <aside className="shell-sidebar">
        <div className="sidebar-brand">
          <span className="eyebrow">VibeCoding Board</span>
          <h2>Admin Console</h2>
          <p>Single-node control surface for upstream routing, health, and request flow.</p>
        </div>

        <nav className="sidebar-nav">
          <button
            type="button"
            className={`nav-item${currentView === 'overview' ? ' nav-item-active' : ''}`}
            onClick={() => setCurrentView('overview')}
          >
            <LayoutDashboard size={18} />
            <span>Overview</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'providers' ? ' nav-item-active' : ''}`}
            onClick={() => setCurrentView('providers')}
          >
            <Cable size={18} />
            <span>Providers</span>
          </button>
          <button
            type="button"
            className={`nav-item${currentView === 'traffic' ? ' nav-item-active' : ''}`}
            onClick={() => setCurrentView('traffic')}
          >
            <ScrollText size={18} />
            <span>Traffic</span>
          </button>
        </nav>

        <div className="sidebar-status">
          <div className="sidebar-status-card">
            <span className="surface-label">Primary provider</span>
            <strong>{dashboard?.primary_provider ?? 'Waiting for runtime'}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="surface-label">Last reload</span>
            <strong>{dashboard ? formatTimestamp(dashboard.reloaded_at) : 'Loading…'}</strong>
          </div>
          <div className="sidebar-status-card">
            <span className="surface-label">Sync state</span>
            <strong>{loading ? 'Refreshing dashboard' : 'Dashboard in sync'}</strong>
          </div>
        </div>
      </aside>

      <div className="shell-main">
        <header className="shell-header">
          <div className="header-copy">
            <span className="eyebrow">Admin</span>
            <h1>{meta.title}</h1>
            <p>{meta.description}</p>
          </div>

          <div className="header-controls">
            <div className="header-meta">
              <div className="meta-chip">
                <span className="surface-label">Proxy endpoint</span>
                <strong>{proxyBase}</strong>
              </div>
              <div className="meta-chip">
                <span className="surface-label">Config path</span>
                <strong>{dashboard?.config_path ?? 'Loading…'}</strong>
              </div>
            </div>

            <div className="header-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  void loadDashboard()
                }}
                disabled={loading}
              >
                <RefreshCw size={16} className={loading ? 'spin-icon' : ''} />
                {loading ? 'Refreshing…' : 'Refresh'}
              </button>

              <button type="button" className="accent-button" onClick={openCreateDrawer}>
                <Plus size={16} />
                Add provider
              </button>

              <button
                type="button"
                className="ghost-button"
                onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
              >
                {theme === 'dark' ? <SunMedium size={16} /> : <MoonStar size={16} />}
                {theme === 'dark' ? 'Light mode' : 'Dark mode'}
              </button>
            </div>
          </div>
        </header>

        {flash ? <div className={`flash-banner flash-banner-${flash.tone}`}>{flash.text}</div> : null}

        <main className="shell-content">
          {!dashboard ? (
            <section className="surface-card loading-state">
              <span className="eyebrow">Runtime</span>
              <h2>{loading ? 'Loading dashboard' : 'Dashboard unavailable'}</h2>
              <p>
                {loading
                  ? 'Collecting the latest runtime snapshot from the local proxy.'
                  : 'The admin UI could not load current state. Retry after the backend is available.'}
              </p>
              {!loading ? (
                <button
                  type="button"
                  className="accent-button"
                  onClick={() => {
                    void loadDashboard()
                  }}
                >
                  Retry
                </button>
              ) : null}
            </section>
          ) : currentView === 'overview' ? (
            <OverviewView
              dashboard={dashboard}
              proxyBase={proxyBase}
              loading={loading}
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
        title={deletingProvider ? `Delete ${deletingProvider.name}?` : 'Delete provider'}
        description={
          deletingProvider
            ? 'This removes the upstream from config.yaml immediately. Ongoing requests keep their current runtime snapshot, but new requests will stop considering this provider.'
            : ''
        }
        busy={busyAction === `delete:${deletingProvider?.name ?? ''}`}
        onCancel={() => setDeletingProvider(null)}
        onConfirm={() => {
          void handleDeleteConfirm()
        }}
      />
    </div>
  )
}
