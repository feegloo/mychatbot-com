/**
 * Minimal Dexie mock for the ui test environment.
 *
 * The ui app imports HomeHero from the frontend package, which transitively
 * pulls in database/instance.ts that imports the real `dexie` package.
 * Since `dexie` is a frontend dependency (not a ui dependency), we stub it
 * here so that vitest can resolve the import without needing dexie installed.
 */

/* eslint-disable @typescript-eslint/no-unused-vars */

class Dexie {
  constructor(_name: string) {}

  version(_n: number) {
    return { stores: (_schema: Record<string, string>) => this }
  }

  table<T>(_name: string) {
    return {
      get: (_key: unknown): Promise<T | undefined> => Promise.resolve(undefined),
      put: (_item: unknown): Promise<unknown> => Promise.resolve(undefined),
      delete: (_key: unknown): Promise<void> => Promise.resolve(),
    }
  }
}

export default Dexie
