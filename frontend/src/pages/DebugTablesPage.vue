<template>
  <div class="debug-page">
    <h1>Database Debug</h1>

    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <template v-else>
      <div class="view-toggle">
        <button :class="{ active: view === 'formatted' }" @click="view = 'formatted'">Formatted</button>
        <button :class="{ active: view === 'json' }" @click="view = 'json'">JSON</button>
      </div>

      <template v-if="view === 'json'">
        <div v-for="table in tableNames" :key="table" class="table-section">
          <h2>{{ table }} ({{ data[table].length }})</h2>
          <pre class="json-block">{{ JSON.stringify(data[table], null, 2) }}</pre>
        </div>
      </template>

      <template v-else>
        <div v-for="table in tableNames" :key="table" class="table-section">
          <h2>{{ table }} ({{ data[table].length }})</h2>
          <div class="table-wrapper" v-if="data[table].length">
            <table>
              <thead>
                <tr>
                  <th v-for="col in columns(table)" :key="col">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in data[table]" :key="i">
                  <td v-for="col in columns(table)" :key="col">
                    <span class="cell" :title="String(row[col] ?? '')">{{ formatCell(row[col]) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty">No rows</p>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { getDebugTables } from "../api";

type Tables = Awaited<ReturnType<typeof getDebugTables>>;

const loading = ref(true);
const error = ref("");
const view = ref<"formatted" | "json">("formatted");
const data = ref<Tables>({
  conversations: [],
  conversation_messages: [],
  suggested_questions: [],
  uploaded_files: [],
});

const tableNames = computed(() => Object.keys(data.value) as (keyof Tables)[]);

function columns(table: keyof Tables) {
  const rows = data.value[table];
  if (!rows.length) return [];
  return Object.keys(rows[0]);
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  const s = String(value);
  return s.length > 120 ? s.slice(0, 120) + "…" : s;
}

onMounted(async () => {
  try {
    data.value = await getDebugTables();
  } catch (e: any) {
    error.value = e?.message || "Failed to load";
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.debug-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  font-family: system-ui, -apple-system, sans-serif;
  color: #e2e8f0;
}
h1 {
  margin-bottom: 16px;
  font-size: 1.5rem;
}
h2 {
  margin: 24px 0 8px;
  font-size: 1.1rem;
  color: #94a3b8;
}
.view-toggle {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
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
.table-wrapper {
  overflow-x: auto;
  border: 1px solid #334155;
  border-radius: 8px;
}
table {
  width: 100%;
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
}
td {
  max-width: 300px;
}
.cell {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
}
.json-block {
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  font-size: 0.8rem;
  max-height: 500px;
  overflow-y: auto;
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
</style>
