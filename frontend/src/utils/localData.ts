const STORAGE_KEY = "data";

function readAll(): Record<string, unknown> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeAll(data: Record<string, unknown>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

export function getData<T>(key: string): T | undefined {
  const all = readAll();
  return all[key] as T | undefined;
}

export function setData(key: string, value: unknown) {
  const all = readAll();
  all[key] = value;
  writeAll(all);
}

/** Migrate old individual localStorage keys into the unified "data" key. */
export function migrateLocalData() {
  const keysToRemove: string[] = [];
  const all = readAll();
  let changed = false;
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;
    if (key.startsWith("quiz:") || key.startsWith("checklist:")) {
      if (!(key in all)) {
        try {
          all[key] = JSON.parse(localStorage.getItem(key)!);
        } catch {
          all[key] = localStorage.getItem(key);
        }
        changed = true;
      }
      keysToRemove.push(key);
    }
  }
  if (changed) writeAll(all);
  for (const key of keysToRemove) {
    localStorage.removeItem(key);
  }
}
