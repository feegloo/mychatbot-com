import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'homePageLang'

async function loadModule() {
  // Re-import in isolation so each test sees a fresh `homeLang` initial value
  // computed from the current localStorage / navigator.language stub.
  vi.resetModules()
  return await import('../../src/i18n/homeLocale')
}

function setBrowserLanguage(lang: string) {
  Object.defineProperty(window.navigator, 'language', {
    configurable: true,
    get: () => lang,
  })
}

describe('homeLocale', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it("defaults to 'pl' when browser language is Polish and nothing stored", async () => {
    setBrowserLanguage('pl-PL')
    const { homeLang } = await loadModule()
    expect(homeLang.value).toBe('pl')
  })

  it("defaults to 'en' for any non-Polish browser language", async () => {
    setBrowserLanguage('de-DE')
    const { homeLang } = await loadModule()
    expect(homeLang.value).toBe('en')
  })

  it('prefers the saved localStorage value over the browser language', async () => {
    setBrowserLanguage('pl-PL')
    localStorage.setItem(STORAGE_KEY, 'en')
    const { homeLang } = await loadModule()
    expect(homeLang.value).toBe('en')
  })

  it('setHomeLang persists to localStorage and updates messages', async () => {
    setBrowserLanguage('en-US')
    const { homeLang, homeT, setHomeLang } = await loadModule()
    expect(homeLang.value).toBe('en')
    expect(homeT.value.askPlaceholder).toBe('Ask your question ...')

    setHomeLang('pl')

    expect(homeLang.value).toBe('pl')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('pl')
    expect(homeT.value.askPlaceholder).toBe('Zadaj swoje pytanie ...')  })

  it('toggleHomeLang flips between en and pl', async () => {
    setBrowserLanguage('en-US')
    const { homeLang, toggleHomeLang } = await loadModule()
    expect(homeLang.value).toBe('en')

    toggleHomeLang()
    expect(homeLang.value).toBe('pl')

    toggleHomeLang()
    expect(homeLang.value).toBe('en')
  })

  it('ignores unsupported language values passed to setHomeLang', async () => {
    setBrowserLanguage('en-US')
    const { homeLang, setHomeLang } = await loadModule()
    // Cast through unknown so the test exercises the runtime guard rather
    // than relying on the compile-time HomeLang union.
    setHomeLang('fr' as unknown as 'en')
    expect(homeLang.value).toBe('en')
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })
})
