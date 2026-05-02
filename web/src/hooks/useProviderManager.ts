import { useState, useCallback, useRef } from 'react'
import type { DashboardResponse, ProviderFormState, ProviderSummary } from '../types'
import type { useDashboard } from './useDashboard'
import { api } from '../api'

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
  supportsResponsesWebsocket: false,
  timeoutSeconds: '60',
  maxFailures: '3',
  cooldownSeconds: '30',
}

export function formFromProvider(provider: ProviderSummary): ProviderFormState {
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
    supportsResponsesWebsocket: provider.supports_responses_websocket,
    timeoutSeconds: String(provider.timeout_seconds),
    maxFailures: String(provider.max_failures),
    cooldownSeconds: String(provider.cooldown_seconds),
  }
}

export function createProviderForm(dashboard: DashboardResponse | null): ProviderFormState {
  return {
    ...emptyForm,
    priority: String(
      dashboard?.providers.length
        ? Math.max(...dashboard.providers.map((provider) => provider.priority)) + 10
        : 10,
    ),
  }
}

export function providerFormsEqual(
  left: ProviderFormState,
  right: ProviderFormState,
): boolean {
  return (
    left.name === right.name &&
    left.baseUrl === right.baseUrl &&
    left.apiKey === right.apiKey &&
    left.enabled === right.enabled &&
    left.alwaysAlive === right.alwaysAlive &&
    left.priority === right.priority &&
    left.modelMode === right.modelMode &&
    left.modelText === right.modelText &&
    left.healthcheckModel === right.healthcheckModel &&
    left.supportsResponsesWebsocket === right.supportsResponsesWebsocket &&
    left.timeoutSeconds === right.timeoutSeconds &&
    left.maxFailures === right.maxFailures &&
    left.cooldownSeconds === right.cooldownSeconds
  )
}

export function useProviderManager(
  dashboard: DashboardResponse | null,
  runMutation: ReturnType<typeof useDashboard>['runMutation'],
  setCurrentView: (view: 'overview' | 'providers' | 'traffic' | 'settings') => void,
  busyAction: string | null
) {
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit' | null>(null)
  const [editingProvider, setEditingProvider] = useState<ProviderSummary | null>(null)
  const [form, setForm] = useState<ProviderFormState>(emptyForm)
  const providerDrawerBusyRef = useRef(false)

  const providerDrawerBusy = busyAction === 'submit' || busyAction === 'provider-autosave'

  const openCreateDrawer = useCallback(() => {
    setCurrentView('providers')
    setEditingProvider(null)
    setForm(createProviderForm(dashboard))
    setDrawerMode('create')
  }, [dashboard, setCurrentView])

  const openEditDrawer = useCallback((provider: ProviderSummary) => {
    setCurrentView('providers')
    setEditingProvider(provider)
    setForm(formFromProvider(provider))
    setDrawerMode('edit')
  }, [setCurrentView])

  const closeDrawer = useCallback(() => {
    if (providerDrawerBusyRef.current || providerDrawerBusy) {
      return
    }
    setDrawerMode(null)
    setEditingProvider(null)
    setForm(createProviderForm(dashboard))
  }, [dashboard, providerDrawerBusy])

  const handleSubmit = useCallback(async (nextForm: ProviderFormState) => {
    if (drawerMode !== 'create') return

    providerDrawerBusyRef.current = true
    const success = await runMutation('submit', () => api.createProvider(nextForm))
    providerDrawerBusyRef.current = false

    if (success) {
      closeDrawer()
    }
  }, [drawerMode, runMutation, closeDrawer])

  const handleProviderAutoSave = useCallback(async (nextForm: ProviderFormState) => {
    if (drawerMode !== 'edit' || busyAction !== null || editingProvider === null) return

    setForm(nextForm)
    if (providerFormsEqual(nextForm, formFromProvider(editingProvider))) return

    providerDrawerBusyRef.current = true
    try {
      await runMutation(
        'provider-autosave',
        () => api.updateProvider(editingProvider.name, nextForm),
        (response) => {
          const updatedProvider =
            response.dashboard.providers.find((provider) => provider.name === nextForm.name.trim()) ??
            response.dashboard.providers.find((provider) => provider.name === editingProvider.name)

          if (!updatedProvider) return

          setEditingProvider(updatedProvider)
          setForm(formFromProvider(updatedProvider))
        },
      )
    } finally {
      providerDrawerBusyRef.current = false
    }
  }, [drawerMode, busyAction, editingProvider, runMutation])

  const handlePromote = useCallback(async (provider: ProviderSummary) => {
    await runMutation(`promote:${provider.name}`, () => api.promoteProvider(provider.name))
  }, [runMutation])

  const handleToggle = useCallback(async (provider: ProviderSummary) => {
    await runMutation(`toggle:${provider.name}`, () => api.toggleProvider(provider.name))
  }, [runMutation])

  const handleToggleAlwaysAlive = useCallback(async (provider: ProviderSummary) => {
    await runMutation(`always-alive:${provider.name}`, () => api.toggleProviderAlwaysAlive(provider.name))
  }, [runMutation])

  const handlePrioritySave = useCallback(async (provider: ProviderSummary, priority: number) => {
    return runMutation(`priority:${provider.name}`, () => api.updateProviderPriority(provider.name, priority))
  }, [runMutation])

  return {
    drawerMode,
    editingProvider,
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
  }
}
