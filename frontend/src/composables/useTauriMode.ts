import { ref, readonly } from 'vue'

export type AppMode = 'cloud' | 'local'

const STORAGE_KEY = 'chatrag-app-mode'
const DEFAULT_MODE: AppMode = 'cloud'
const VALID_MODES: ReadonlySet<string> = new Set<AppMode>(['cloud', 'local'])

/** True when the Vue app is running inside a Tauri shell. */
export function isTauriEnv(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

function readStoredMode(): AppMode {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored !== null && VALID_MODES.has(stored) ? (stored as AppMode) : DEFAULT_MODE
}

// Module-level singletons so every component shares the same reactive state.
const _isTauri = isTauriEnv()
const _mode = ref<AppMode>(_isTauri ? readStoredMode() : DEFAULT_MODE)

export function useTauriMode() {
  function setMode(mode: AppMode) {
    _mode.value = mode
    if (_isTauri) {
      localStorage.setItem(STORAGE_KEY, mode)
    }
  }

  return {
    isTauri: _isTauri,
    mode: readonly(_mode),
    setMode,
  }
}
