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
