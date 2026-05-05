import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// In-memory store backing the mocked ConfigurationsTable.
const configStore = new Map<string, string>()

vi.mock('../../src/utils/database', () => ({
  ConfigurationsTable: {
    get: vi.fn(async (key: string) => configStore.get(key) ?? null),
    set: vi.fn(async (key: string, value: string) => {
      configStore.set(key, value)
    }),
  },
}))

async function loadModule() {
  // Re-import in isolation so each test sees a fresh `homeLang` initial value
  // computed from the current navigator.language stub.
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
    configStore.clear()
  })

  afterEach(() => {
    configStore.clear()
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

  it('prefers the saved value over the browser language when initHomeLang is called', async () => {
    setBrowserLanguage('pl-PL')
    configStore.set('homePageLang', 'en') // pre-seed IndexedDB with saved preference
    const { homeLang, initHomeLang } = await loadModule()
    expect(homeLang.value).toBe('pl') // starts with browser default before init
    await initHomeLang() // loads from (mocked) IndexedDB
    expect(homeLang.value).toBe('en') // overridden by persisted preference
  })

  it('setHomeLang updates homeLang and messages', async () => {
    setBrowserLanguage('en-US')
    const { homeLang, homeT, setHomeLang } = await loadModule()
    expect(homeLang.value).toBe('en')
    expect(homeT.value.askPlaceholder).toBe('Ask your question ...')

    await setHomeLang('pl')

    expect(homeLang.value).toBe('pl')
    expect(homeT.value.askPlaceholder).toBe('Zadaj swoje pytanie ...')
  })

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
    expect(configStore.get('homePageLang')).toBeUndefined()
  })
})
