export type ThemePreference = 'auto' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'admin-theme-preference'

export function loadThemePreference(): ThemePreference {
  if (typeof window === 'undefined') {
    return 'auto'
  }

  const value = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (value === 'auto' || value === 'light' || value === 'dark') {
    return value
  }
  return 'auto'
}

export function saveThemePreference(preference: ThemePreference): void {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(THEME_STORAGE_KEY, preference)
}

export function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') {
    return 'light'
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function resolveTheme(
  preference: ThemePreference,
  systemTheme: ResolvedTheme,
): ResolvedTheme {
  if (preference === 'auto') {
    return systemTheme
  }
  return preference
}
