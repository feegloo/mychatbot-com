<template>
  <div class="debug-page">
    <h1>Database Debug</h1>

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
          <button :class="{ active: view === 'formatted' }" @click="view = 'formatted'">Formatted</button>
          <button :class="{ active: view === 'json' }" @click="view = 'json'">JSON</button>
        </div>
      </div>

      <div class="table-section">
        <template v-if="view === 'json'">
          <pre class="json-block">{{ JSON.stringify(data[activeTable], null, 2) }}</pre>
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
                    <span class="cell" :title="String(row[col] ?? '')">{{ formatCell(row[col]) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty">No rows</p>
        </template>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
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
