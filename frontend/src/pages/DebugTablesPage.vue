<template>
  <div class="debug-page">
    <div v-if="!authenticated" class="login-box">
      <h2>Login required</h2>
      <form @submit.prevent="doLogin">
        <input v-model="username" type="text" placeholder="Username" autocomplete="username" />
        <input v-model="password" type="password" placeholder="Password" autocomplete="current-password" />
        <button type="submit" :disabled="loginLoading">{{ loginLoading ? 'Logging in…' : 'Login' }}</button>
      </form>
      <p v-if="loginError" class="error">{{ loginError }}</p>
    </div>

    <div v-else-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <template v-else>
      <div class="controls">
        <div class="table-tabs">
          <button
            v-for="table in tableNames"
            :key="table"
            :class="{ active: activeTable === table }"
            @click="activeTable = table"
          >
            {{ table }} <span class="count">({{ data[table].length }})</span>
          </button>
        </div>
        <div class="view-toggle">
          <button :class="{ active: view === 'json' }" @click="view = view === 'json' ? 'formatted' : 'json'">{{ view === 'json' ? 'Table' : 'JSON' }}</button>
        </div>
      </div>

      <div class="table-section">
        <template v-if="view === 'json'">
          <div class="table-wrapper">
            <pre class="json-block">{{ JSON.stringify(data[activeTable], null, 2) }}</pre>
          </div>
        </template>

        <template v-else>
          <div class="table-wrapper" v-if="data[activeTable].length">
            <table>
              <thead>
                <tr>
                  <th v-for="col in columns(activeTable)" :key="col">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in data[activeTable]" :key="i">
                  <td v-for="col in columns(activeTable)" :key="col">
                    <span
                      class="cell"
                      :class="{ expanded: isCellExpanded(i, col) }"
                      :title="isCellExpanded(i, col) ? '' : String(row[col] ?? '')"
                      @click="toggleCell(i, col, row[col])"
                    >{{ isCellExpanded(i, col) ? expandedCellContent(row[col]) : formatCell(row[col]) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty">No rows</p>
        </template>

        <div v-if="canLoadMore" class="load-more-wrapper">
          <button class="load-more-btn" :disabled="loadingMore" @click="loadMore">
            {{ loadingMore ? 'Loading…' : 'Load 1000 more rows' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { getDebugTables } from "../api";

type Tables = Awaited<ReturnType<typeof getDebugTables>>;

const authenticated = ref(false);
const username = ref("");
const password = ref("");
const loginLoading = ref(false);
const loginError = ref("");

const loading = ref(true);
const error = ref("");
const view = ref<"formatted" | "json">("formatted");
const activeTable = ref<keyof Tables>("conversations");
const loadingMore = ref(false);
const currentOffset = ref(0);
const data = ref<Tables>({
  conversations: [],
  conversation_messages: [],
  suggested_questions: [],
  uploaded_files: [],
  user_fingerprints: [],
  conversation_access_tokens: [],
  access_requests: [],
  users: [],
});

const expandedCells = ref<Set<string>>(new Set());

watch(activeTable, () => {
  expandedCells.value = new Set();
});

const tableNames = computed(() => Object.keys(data.value) as (keyof Tables)[]);

function columns(table: keyof Tables) {
  const rows = data.value[table];
  if (!rows.length) return [];
  return Object.keys(rows[0]);
}

function cellKey(row: number, col: string) {
  return `${row}:${col}`;
}

function isCellExpanded(row: number, col: string) {
  return expandedCells.value.has(cellKey(row, col));
}

function toggleCell(row: number, col: string, _value: unknown) {
  const key = cellKey(row, col);
  const next = new Set(expandedCells.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  expandedCells.value = next;
}

function isJsonString(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try { JSON.parse(trimmed); return true; } catch { return false; }
  }
  return false;
}

function expandedCellContent(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  const s = String(value);
  if (isJsonString(s)) {
    try { return JSON.stringify(JSON.parse(s), null, 2); } catch { /* fall through */ }
  }
  return s;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  const s = String(value);
  return s.length > 120 ? s.slice(0, 120) + "…" : s;
}

// "users" is an aggregate query, not paginated
const paginatedTables: (keyof Tables)[] = [
  "conversations", "conversation_messages", "suggested_questions",
  "uploaded_files", "user_fingerprints", "conversation_access_tokens", "access_requests",
];

const canLoadMore = computed(() => {
  if (activeTable.value === "users") return false;
  // Show button if the last fetch returned a full page (1000) for this table
  return data.value[activeTable.value].length > 0 && data.value[activeTable.value].length % 1000 === 0;
});

async function loadMore() {
  loadingMore.value = true;
  try {
    const nextOffset = currentOffset.value + 1000;
    const more = await getDebugTables(username.value, password.value, nextOffset);
    currentOffset.value = nextOffset;
    for (const table of paginatedTables) {
      if (more[table].length) {
        data.value[table] = [...data.value[table], ...more[table]];
      }
    }
    // Always replace aggregate data
    data.value.users = more.users;
  } catch (e: any) {
    error.value = e?.message || "Failed to load more";
  } finally {
    loadingMore.value = false;
  }
}

async function doLogin() {
  loginLoading.value = true;
  loginError.value = "";
  try {
    data.value = await getDebugTables(username.value, password.value);
    authenticated.value = true;
    loading.value = false;
  } catch (e: any) {
    if (e?.response?.status === 401) {
      loginError.value = "Invalid credentials";
    } else {
      loginError.value = e?.message || "Failed to load";
    }
  } finally {
    loginLoading.value = false;
  }
}
</script>

<style scoped>
.debug-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  font-family: system-ui, -apple-system, sans-serif;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px);
}
h1 {
  margin-bottom: 16px;
  font-size: 1.5rem;
}
.controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}
.table-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.table-tabs button {
  padding: 8px 16px;
  border: 1px solid #334155;
  border-bottom: 2px solid transparent;
  border-radius: 6px 6px 0 0;
  background: #1e293b;
  color: #94a3b8;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
}
@media (hover: hover) {
  .table-tabs button:hover {
    background: #273449;
  }
}
.table-tabs button:active {
  background: #273449;
}
.table-tabs button.active {
  background: #334155;
  color: #f1f5f9;
  border-bottom-color: #818cf8;
}
.table-tabs .count {
  opacity: 0.6;
  font-size: 0.8em;
}
.login-box {
  max-width: 320px;
  margin: 80px auto;
  padding: 24px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #1e293b;
}
.login-box h2 {
  margin: 0 0 16px;
  font-size: 1.1rem;
  color: #94a3b8;
}
.login-box form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.login-box input {
  padding: 8px 12px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 0.9rem;
}
.login-box button {
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  background: #818cf8;
  color: #fff;
  cursor: pointer;
  font-size: 0.9rem;
}
.login-box button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.view-toggle {
  display: flex;
  gap: 8px;
}
.view-toggle button {
  padding: 6px 16px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #1e293b;
  color: #94a3b8;
  cursor: pointer;
  font-size: 0.85rem;
}
.view-toggle button.active {
  background: #334155;
  color: #f1f5f9;
}
.table-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.table-wrapper {
  flex: 1;
  overflow: auto;
  min-height: 0;
  border: 1px solid #334155;
  border-radius: 8px;
}
table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 0.8rem;
}
th, td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid #1e293b;
  white-space: nowrap;
}
th {
  background: #1e293b;
  color: #94a3b8;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}
td {
  max-width: 300px;
}
.cell {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
  cursor: pointer;
}
.cell.expanded {
  white-space: pre-wrap;
  word-break: break-word;
  overflow: visible;
  text-overflow: unset;
  max-width: none;
}
td:has(.cell.expanded) {
  white-space: normal;
  max-width: none;
}
.json-block {
  background: #0f172a;
  margin: 0;
  padding: 12px;
  font-size: 0.8rem;
  white-space: pre-wrap;
  word-break: break-word;
}
.loading {
  color: #94a3b8;
  padding: 32px;
}
.error {
  color: #f87171;
  padding: 16px;
}
.empty {
  color: #64748b;
  font-style: italic;
}
.load-more-wrapper {
  display: flex;
  justify-content: center;
  padding: 16px 0;
  flex-shrink: 0;
}
.load-more-btn {
  padding: 8px 24px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #1e293b;
  color: #94a3b8;
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
}
.load-more-btn:hover {
  background: #334155;
  color: #f1f5f9;
}
.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
