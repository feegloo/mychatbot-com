<template>
  <Teleport to="body">
    <Transition name="local-modal">
      <div v-if="show" class="local-modal-backdrop" @click.self="$emit('close')">
        <div class="local-modal" role="dialog" aria-modal="true" aria-labelledby="local-modal-title">
          <button class="local-modal-close" aria-label="Close" @click="$emit('close')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>

          <div class="local-modal-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="4" width="18" height="12" rx="2" />
              <polyline points="8 20 12 16 16 20" />
              <line x1="12" y1="16" x2="12" y2="20" />
            </svg>
          </div>

          <h2 id="local-modal-title" class="local-modal-title">Run ChatRAG locally</h2>

          <p class="local-modal-body">
            Local mode keeps all your files and conversations on your Mac — nothing is sent to the cloud.
            <br /><br />
            Download <strong>ChatRAG.dmg</strong> to run the full ChatRAG backend on your machine. Once running, switch this browser to Local mode and your conversations will be routed through <code>localhost</code>.
          </p>

          <div class="local-modal-actions">
            <a
              href="https://chatrag.app/download/ChatRAG.dmg"
              class="local-modal-btn local-modal-btn--primary"
              download
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Download ChatRAG.dmg
            </a>
            <button class="local-modal-btn local-modal-btn--secondary" @click="$emit('close')">
              Stay in Cloud mode
            </button>
          </div>

          <p class="local-modal-note">
            macOS 13+&nbsp;•&nbsp;Apple Silicon &amp; Intel&nbsp;•&nbsp;Free
          </p>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{ show: boolean }>()
defineEmits<{ close: [] }>()
</script>

<style scoped>
.local-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0, 0, 0, 0.62);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.local-modal {
  background: #0f172a;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 18px;
  padding: 32px 28px 24px;
  max-width: 400px;
  width: 100%;
  position: relative;
  text-align: center;
  box-shadow:
    0 24px 64px rgba(0, 0, 0, 0.6),
    0 0 0 0.5px rgba(255, 255, 255, 0.06) inset;
}

.local-modal-close {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 28px;
  height: 28px;
  border: none;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 50%;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}
.local-modal-close:hover {
  background: rgba(255, 255, 255, 0.14);
  color: #e2e8f0;
}

.local-modal-icon {
  color: #818cf8;
  margin-bottom: 16px;
  display: flex;
  justify-content: center;
}

.local-modal-title {
  font-size: 20px;
  font-weight: 700;
  color: #f1f5f9;
  margin: 0 0 12px;
}

.local-modal-body {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.6;
  margin: 0 0 24px;
}

.local-modal-body code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.08);
  padding: 1px 5px;
  border-radius: 4px;
  color: #a5b4fc;
}

.local-modal-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.local-modal-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 11px 20px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  transition: opacity 0.15s, transform 0.15s;
  border: none;
}
.local-modal-btn:active {
  transform: scale(0.97);
}

.local-modal-btn--primary {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
}
.local-modal-btn--primary:hover {
  opacity: 0.88;
}

.local-modal-btn--secondary {
  background: rgba(255, 255, 255, 0.07);
  color: #94a3b8;
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.local-modal-btn--secondary:hover {
  background: rgba(255, 255, 255, 0.11);
  color: #cbd5e1;
}

.local-modal-note {
  font-size: 12px;
  color: #475569;
  margin: 0;
}

/* Transition */
.local-modal-enter-active,
.local-modal-leave-active {
  transition: opacity 0.2s ease;
}
.local-modal-enter-active .local-modal,
.local-modal-leave-active .local-modal {
  transition: transform 0.22s cubic-bezier(0.34, 1.2, 0.64, 1), opacity 0.2s ease;
}
.local-modal-enter-from,
.local-modal-leave-to {
  opacity: 0;
}
.local-modal-enter-from .local-modal,
.local-modal-leave-to .local-modal {
  transform: scale(0.94) translateY(8px);
  opacity: 0;
}
</style>
