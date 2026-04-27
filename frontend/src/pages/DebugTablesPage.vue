<template>
  <div class="debug-page">
    <div v-if="!authenticated" class="login-box">
      <h2>Login required</h2>
      <form @submit.prevent="doLogin">
        <input v-model="username" type="text" placeholder="Username" autocomplete="username" />
        <input
          v-model="password"
          type="password"
          placeholder="Password"
          autocomplete="current-password"
        />
        <button type="submit" :disabled="loginLoading">
          {{ loginLoading ? 'Logging in…' : 'Login' }}
        </button>
      </form>
      <p v-if="loginError" class="error">{{ loginError }}</p>
    </div>

    <div v-else-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <template v-else>
      <div class="controls">
        <div class="table-tabs">
          <button
            v-for="table in visibleTableNames"
            :key="table"
            :class="{ active: activeTable === table }"
            @click="activeTable = table"
          >
            {{ table }} <span class="count">({{ counts[table] ?? 0 }})</span>
          </button>
          <button
            v-if="isMobile"
            class="tabs-toggle"
            @click="tabsExpanded = !tabsExpanded"
          >
            {{ tabsExpanded ? '▲ Less' : `▼ +${TABLE_NAMES.length - MOBILE_VISIBLE_TABS}` }}
          </button>
          <button :class="{ active: activeTable === SQL_TAB }" @click="activeTable = SQL_TAB">
            Run SQL query
          </button>
        </div>
        <div class="view-toggle">
          <button
            :class="{ active: view === 'json' }"
            @click="view = view === 'json' ? 'formatted' : 'json'"
          >
            {{ view === 'json' ? 'Table' : 'JSON' }}
          </button>
        </div>
      </div>

      <div v-if="activeTable === SQL_TAB" class="sql-panel">
        <textarea
          v-model="sqlInput"
          class="sql-input"
          spellcheck="false"
          placeholder="SELECT * FROM conversations ORDER BY created_at DESC LIMIT 50"
          @keydown.meta.enter.prevent="runSql"
          @keydown.ctrl.enter.prevent="runSql"
        />
        <div class="sql-actions">
          <button class="run-btn" :disabled="sqlLoading || !sqlInput.trim()" @click="runSql">
            {{ sqlLoading ? 'Running…' : 'RUN' }}
          </button>
          <span v-if="sqlResult" class="sql-meta">
            {{ sqlResult.command }} · {{ sqlResult.rows.length }} rows ·
            {{ sqlResult.durationMs }} ms
          </span>
        </div>
        <p v-if="sqlError" class="error">{{ sqlError }}</p>

        <div class="table-section">
          <template v-if="sqlResult && view === 'json'">
            <div class="table-wrapper">
              <pre class="json-block">{{ JSON.stringify(sqlResult.rows, null, 2) }}</pre>
            </div>
          </template>
          <template v-else-if="sqlResult && sqlResult.rows.length">
            <div class="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th v-for="col in sqlResult.fields" :key="col" :class="{ 'col-content': col === 'content' }">{{ col }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in sqlResult.rows" :key="i">
                    <td v-for="col in sqlResult.fields" :key="col" :class="{ 'col-content': col === 'content' }">
                      <span class="cell" :title="String(row[col] ?? '')">{{
                        formatCell(row[col])
                      }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
          <p v-else-if="sqlResult" class="empty">No rows</p>
        </div>
      </div>

      <div v-else class="table-section">
        <p v-if="isLoadingCurrentTable" class="loading">Loading…</p>
        <template v-else-if="view === 'json'">
          <div class="table-wrapper">
            <pre class="json-block">{{ JSON.stringify(currentRows, null, 2) }}</pre>
          </div>
        </template>

        <template v-else>
          <div v-if="currentRows.length" class="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th v-for="col in currentColumns" :key="col" :class="{ 'col-content': col === 'content' }">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in currentRows"
                  :key="i"
                  :class="{ 'row-expanded': isRowExpanded(i) }"
                  class="data-row"
                  @click="toggleRow(i, row)"
                >
                  <td v-for="col in currentColumns" :key="col" :class="{ 'col-content': col === 'content' }">
                    <span
                      class="cell"
                      :class="{ expanded: isRowExpanded(i) }"
                      :title="isRowExpanded(i) ? '' : String(row[col] ?? '')"
                    >
                      {{ renderCell(row, col, isRowExpanded(i)) }}
                    </span>
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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  getDebugTable,
  getDebugTablesOverview,
  getFullPrompt,
  runDebugSql,
  type DebugTableName,
} from '../api'

type TableMap = Record<DebugTableName, Record<string, unknown>[]>
type Counts = Record<DebugTableName, number>
type SqlResult = Awaited<ReturnType<typeof runDebugSql>>

const SQL_TAB = '__sql__' as const
type TabKey = DebugTableName | typeof SQL_TAB

const TABLE_NAMES: DebugTableName[] = [
  'conversations',
  'conversation_messages',
  'suggested_questions',
  'uploaded_files',
  'user_fingerprints',
  'conversation_access_tokens',
  'access_requests',
  'users',
  'processing_jobs',
  'processing_jobs_errors',
  'prompt_history',
  'generated_images',
  'indexing_events',
  'pdf_pages',
  'workers',
  'jobs',
]

const MOBILE_VISIBLE_TABS = 3

const isMobile = ref(typeof window !== 'undefined' && window.innerWidth < 768)
const tabsExpanded = ref(false)

const handleResize = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

const visibleTableNames = computed(() => {
  if (!isMobile.value || tabsExpanded.value) return TABLE_NAMES
  const visibleNames = TABLE_NAMES.slice(0, MOBILE_VISIBLE_TABS)
  const current = activeTable.value
  if (current === SQL_TAB || visibleNames.includes(current as DebugTableName)) {
    return visibleNames
  }
  return [...visibleNames.slice(0, MOBILE_VISIBLE_TABS - 1), current as DebugTableName]
})

const authenticated = ref(false)
const username = ref('')
const password = ref('')
const loginLoading = ref(false)
const loginError = ref('')

const loading = ref(true)
const error = ref('')
const view = ref<'formatted' | 'json'>('formatted')
const activeTable = ref<TabKey>('conversations')
const loadingMore = ref(false)
// Tables that have been fetched or are currently fetching, to avoid
// re-requesting them every time the user switches tabs.
const fetchedTables = ref<Set<DebugTableName>>(new Set())
const loadingTable = ref<DebugTableName | null>(null)
// Per-table offset for "Load more" pagination.
const tableOffsets = ref<Record<DebugTableName, number>>(emptyOffsets())
const counts = ref<Counts>(emptyCounts())
const data = ref<TableMap>(emptyTableMap())

const expandedRows = ref<Set<number>>(new Set())
// keyed by prompt_history row id → full text fields
const fullPromptCache = ref<Map<string, { prompt_text: string; response_text: string }>>(new Map())

function emptyTableMap(): TableMap {
  return TABLE_NAMES.reduce((acc, name) => {
    acc[name] = []
    return acc
  }, {} as TableMap)
}

function emptyCounts(): Counts {
  return TABLE_NAMES.reduce((acc, name) => {
    acc[name] = 0
    return acc
  }, {} as Counts)
}

function emptyOffsets(): Record<DebugTableName, number> {
  return TABLE_NAMES.reduce(
    (acc, name) => {
      acc[name] = 0
      return acc
    },
    {} as Record<DebugTableName, number>,
  )
}

watch(activeTable, async (table) => {
  expandedRows.value = new Set()
  if (table === SQL_TAB) return
  if (fetchedTables.value.has(table) || loadingTable.value === table) return
  await fetchTable(table)
})

async function fetchTable(name: DebugTableName) {
  loadingTable.value = name
  try {
    const { rows } = await getDebugTable(username.value, password.value, name)
    data.value[name] = rows
    fetchedTables.value = new Set([...fetchedTables.value, name])
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load table'
  } finally {
    loadingTable.value = null
  }
}

const isLoadingCurrentTable = computed(
  () => activeTable.value !== SQL_TAB && loadingTable.value === activeTable.value,
)

const currentRows = computed(() =>
  activeTable.value === SQL_TAB ? [] : data.value[activeTable.value as DebugTableName],
)

const currentColumns = computed(() => {
  if (activeTable.value === SQL_TAB) return [] as string[]
  return columns(activeTable.value as DebugTableName)
})

function columns(table: DebugTableName) {
  const rows = data.value[table]
  if (!rows.length) return []
  return Object.keys(rows[0])
}

function isRowExpanded(rowIdx: number) {
  return expandedRows.value.has(rowIdx)
}

async function toggleRow(rowIdx: number, rowLike: unknown) {
  const row = rowLike as Record<string, unknown>
  const next = new Set(expandedRows.value)
  if (next.has(rowIdx)) {
    next.delete(rowIdx)
    expandedRows.value = next
    return
  }
  next.add(rowIdx)
  expandedRows.value = next

  if (activeTable.value === 'prompt_history') {
    const id = String(row.id ?? '')
    if (id && !fullPromptCache.value.has(id)) {
      try {
        const full = await getFullPrompt(username.value, password.value, id)
        const updated = new Map(fullPromptCache.value)
        updated.set(id, full)
        fullPromptCache.value = updated
      } catch {
        // fallback: already have 300-char preview in the row
      }
    }
  }
}

function fullCellContent(row: Record<string, unknown>, col: string): string {
  if (activeTable.value === 'prompt_history' && TEXT_PREVIEW_COLS.has(col)) {
    const id = String(row.id ?? '')
    const cached = fullPromptCache.value.get(id)
    if (cached) return String(cached[col as keyof typeof cached] ?? '—')
  }
  return expandedCellContent(row[col])
}

/** Template-facing cell renderer. Accepts `unknown` so the template doesn't
 *  need an inline `as Record<…>` cast (Prettier's HTML parser mis-reads the
 *  `<` in generics as a stray closing tag). */
function renderCell(row: unknown, col: string, expanded: boolean): string {
  const r = row as Record<string, unknown>
  return expanded ? fullCellContent(r, col) : formatCell(r[col], col)
}

function isJsonString(value: unknown): boolean {
  if (typeof value !== 'string') return false
  const trimmed = value.trim()
  if (
    (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
    (trimmed.startsWith('[') && trimmed.endsWith(']'))
  ) {
    try {
      JSON.parse(trimmed)
      return true
    } catch {
      return false
    }
  }
  return false
}

function expandedCellContent(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  const s = String(value)
  if (isJsonString(s)) {
    try {
      return JSON.stringify(JSON.parse(s), null, 2)
    } catch {
      /* fall through */
    }
  }
  return s
}

const TEXT_PREVIEW_COLS = new Set(['prompt_text', 'response_text'])

function formatCell(value: unknown, col?: string): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  const s = String(value)
  const limit = col && TEXT_PREVIEW_COLS.has(col) ? 300 : 120
  return s.length > limit ? s.slice(0, limit) + '…' : s
}

const canLoadMore = computed(() => {
  if (activeTable.value === SQL_TAB) return false
  if (activeTable.value === 'users') return false
  const name = activeTable.value as DebugTableName
  const loaded = data.value[name].length
  const total = counts.value[name] ?? 0
  return loaded > 0 && loaded < total
})

const sqlInput = ref('SELECT * FROM public.conversations ORDER BY created_at DESC LIMIT 50;')
const sqlLoading = ref(false)
const sqlError = ref('')
const sqlResult = ref<SqlResult | null>(null)

async function runSql() {
  const sql = sqlInput.value.trim()
  if (!sql) return
  sqlLoading.value = true
  sqlError.value = ''
  try {
    sqlResult.value = await runDebugSql(username.value, password.value, sql)
  } catch (e: unknown) {
    sqlResult.value = null
    if (e instanceof Error && 'response' in e) {
      const resp = (e as { response?: { data?: { error?: string }; status?: number } }).response
      sqlError.value = resp?.data?.error ?? e.message
    } else {
      sqlError.value = e instanceof Error ? e.message : 'Query failed'
    }
  } finally {
    sqlLoading.value = false
  }
}

async function loadMore() {
  if (activeTable.value === SQL_TAB || activeTable.value === 'users') return
  const name = activeTable.value as DebugTableName
  loadingMore.value = true
  try {
    const nextOffset = tableOffsets.value[name] + 1000
    const { rows } = await getDebugTable(username.value, password.value, name, nextOffset)
    tableOffsets.value[name] = nextOffset
    if (rows.length) {
      data.value[name] = [...data.value[name], ...rows]
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : 'Failed to load more'
  } finally {
    loadingMore.value = false
  }
}

async function doLogin() {
  loginLoading.value = true
  loginError.value = ''
  try {
    const overview = await getDebugTablesOverview(username.value, password.value)
    counts.value = overview.counts
    data.value.conversations = overview.conversations
    fetchedTables.value = new Set<DebugTableName>(['conversations'])
    authenticated.value = true
    loading.value = false
  } catch (e: unknown) {
    if (e instanceof Error && 'response' in e) {
      const resp = (e as { response?: { status?: number } }).response
      if (resp?.status === 401) {
        loginError.value = 'Invalid credentials'
      } else {
        loginError.value = e.message || 'Failed to load'
      }
    } else {
      loginError.value = e instanceof Error ? e.message : 'Failed to load'
    }
  } finally {
    loginLoading.value = false
  }
}
</script>

<style scoped>
.debug-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  font-family:
    system-ui,
    -apple-system,
    sans-serif;
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px);
}
@media (max-width: 767px) {
  .debug-page {
    padding: 8px;
    height: calc(100vh - 16px);
  }
}
h1 {
  margin-bottom: 16px;
  font-size: 1.5rem;
}
.controls {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 767px) {
  .controls {
    margin-bottom: 6px;
  }
}
.table-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  min-width: 0;
}
@media (max-width: 767px) {
  .table-tabs {
    flex-wrap: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    /* hide scrollbar but keep functionality */
    scrollbar-width: none;
  }
  .table-tabs::-webkit-scrollbar {
    display: none;
  }
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
.tabs-toggle {
  padding: 8px 12px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #818cf8;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 600;
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
  min-width: 100%;
  width: max-content;
  table-layout: auto;
  border-collapse: collapse;
  font-size: 0.8rem;
}
th,
td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid #1e293b;
  white-space: nowrap;
  min-width: 50px;
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
.col-content {
  min-width: 280px;
  max-width: none;
}
.col-content .cell {
  max-width: 500px;
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
.data-row {
  cursor: pointer;
}
@media (hover: hover) {
  .data-row:hover {
    background: #1a2437;
  }
}
.data-row.row-expanded {
  background: #1a2d4a;
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
.sql-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 10px;
}
.sql-input {
  width: 100%;
  min-height: 120px;
  resize: vertical;
  padding: 10px 12px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #e2e8f0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.85rem;
  line-height: 1.4;
}
.sql-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.run-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  background: #818cf8;
  color: #fff;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
}
.run-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.sql-meta {
  color: #94a3b8;
  font-size: 0.8rem;
}
</style>
