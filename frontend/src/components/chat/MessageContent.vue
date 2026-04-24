<script setup lang="ts">
/**
 * Renders a parsed assistant message: markdown text interleaved with
 * `[prompt:…]` (Action) and `[action:…]` (MessageContentAction) tokens,
 * with overflow actions collapsed into MessageContentActionMore. Also
 * handles inline quiz / mermaid blocks via async-loaded child components,
 * plus delegated clicks for [source:N] citations, inline images, the
 * [upload] button, and checklist boxes.
 */
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createTooltip, destroyTooltip } from 'floating-vue'
import type { ChatMessage } from '../../api'
import { applyWordReveal } from '../../composables/wordReveal'
import { parseMessageContent, splitTokens } from './parseContent'
import { splitContent } from './splitContent'
import Action from './Action.vue'
import MessageContentAction from './MessageContentAction.vue'
import MessageContentActionMore from './MessageContentActionMore.vue'

const QuizBlock = defineAsyncComponent(() => import('../QuizBlock.vue'))
const MermaidBlock = defineAsyncComponent(() => import('../MermaidBlock.vue'))

const props = defineProps<{
  content: string
  isWelcome?: boolean
  /** Forwarded to QuizBlock for results submission and PDF export. */
  messageId?: string
  conversationName?: string
  fileName?: string
  /** When provided, hovering `[source:N]` buttons shows the citation text as
   *  a floating-vue tooltip (restored from the pre-refactor ChatMessage). */
  citations?: ChatMessage['citations']
  /** When true, runs the one-shot word-reveal animation on mount.
   *  Set only for newly-arrived messages; the parent clears it after
   *  the `animated` event fires to prevent replaying on translation re-mounts. */
  animate?: boolean
}>()
const emit = defineEmits<{
  /** A `[prompt:Label]` or `[action:Label]` was clicked. */
  select: [label: string]
  /** An inline `<img>` inside the rendered markdown was clicked. */
  'image-click': [src: string, alt: string]
  /** A `[source:N]` button was clicked; payload is the 0-based citation index. */
  'citation-click': [index: number]
  /** The inline `[upload]` button was clicked. */
  'upload-trigger': []
  /** An inline `<img>` inside the rendered markdown finished loading. */
  'image-loaded': []
  /** Fired once, immediately after the word-reveal animation has been applied
   *  on this mount. Parent uses this to clear the `animate` flag so future
   *  re-mounts (e.g. translation) do not replay the animation. */
  animated: []
}>()

// First strip [prompt:] / [action:] tokens out of the raw content so they
// render as Vue components instead of inline HTML buttons.
const parsedTokens = computed(() =>
  splitTokens(parseMessageContent(props.content), !!props.isWelcome),
)
// Then split the remaining text into ordered text/quiz/mermaid parts.
const parts = computed(() => {
  const joined = parsedTokens.value.text.map((t) => t.value).join('\n\n')
  return splitContent(joined)
})

const hasPrompts = computed(() => parsedTokens.value.visiblePrompts.length > 0)
const hasActions = computed(
  () =>
    parsedTokens.value.visibleActions.length > 0 ||
    parsedTokens.value.overflowActions.length > 0,
)

function onContentClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  // Inline images: open lightbox via parent.
  const img = target.closest('img') as HTMLImageElement | null
  if (img && img.src) {
    emit('image-click', img.src, img.alt || 'Image')
    return
  }
  // Source citation buttons: rendered by renderMarkdown as `.inline-source-btn`.
  const sourceBtn = target.closest('.inline-source-btn') as HTMLElement | null
  if (sourceBtn) {
    const idx = parseInt(sourceBtn.dataset.sourceIdx || '0', 10) - 1
    if (idx >= 0) emit('citation-click', idx)
    return
  }
  // Upload button: rendered by renderMarkdown for `[upload]` markers.
  const uploadBtn = target.closest<HTMLElement>('.action-btn[data-upload]')
  if (uploadBtn) {
    emit('upload-trigger')
    return
  }
  // Checklist boxes: toggle in place. (LS persistence dropped in Phase 2 rewrite.)
  const checkBox = target.closest('.checklist-box') as HTMLElement | null
  if (checkBox) {
    checkBox.classList.toggle('checked')
    return
  }
  const li = target.closest('li') as HTMLElement | null
  if (li && li.querySelector('.checklist-box')) {
    li.querySelector('.checklist-box')!.classList.toggle('checked')
  }
}

// --- Inline source citation tooltips --------------------------------------
// Attach floating-vue tooltips to `.inline-source-btn` nodes so hovering a
// citation reveals the source text (restored from the pre-refactor
// implementation). We track the HTMLElements we've attached to so we can
// tear them down before the rendered markdown is re-created on content or
// citation change.
const rootEl = ref<HTMLElement | null>(null)
const tooltipTargets: HTMLElement[] = []
const MAX_TOOLTIP_LENGTH = 600

function truncate(text: string, max: number) {
  return text.length <= max ? text : text.slice(0, max) + '…'
}

function cleanupTooltips() {
  for (const el of tooltipTargets) {
    try {
      destroyTooltip(el)
    } catch {
      /* already destroyed */
    }
  }
  tooltipTargets.length = 0
}

function setupTooltips() {
  cleanupTooltips()
  const citations = props.citations
  if (!citations?.length || !rootEl.value) return
  const buttons = rootEl.value.querySelectorAll<HTMLElement>('.inline-source-btn')
  buttons.forEach((btn) => {
    const idx = parseInt(btn.dataset.sourceIdx || '0', 10) - 1
    const text = citations[idx]?.text
    if (!text) return
    createTooltip(
      btn,
      {
        content: truncate(text, MAX_TOOLTIP_LENGTH),
        delay: { show: 750, hide: 0 },
        themes: ['tooltip'],
      },
      false,
    )
    tooltipTargets.push(btn)
  })
}

// Re-attach after every render that could swap out the citation buttons:
// content string changes (new message or translation) and citations array
// changes (streaming in).
watch(
  () => [props.content, props.citations] as const,
  () => {
    nextTick(setupTooltips)
  },
  { immediate: true, flush: 'post' },
)

// --- Word-reveal "typing" animation --------------------------------------
// Runs once on mount when `animate` is true (new message) and immediately
// signals the parent via `animated` so the parent can clear the flag before
// any future re-mount (e.g. translation) would replay the animation.
// Using onMounted (not a watcher) guarantees it fires exactly once per
// component lifetime with no nextTick needed — the DOM is fully ready.
onMounted(() => {
  if (!props.animate || !rootEl.value) return
  rootEl.value
    .querySelectorAll<HTMLElement>('.markdown-content')
    .forEach((el) => applyWordReveal(el))
  emit('animated')
})

// --- Inline image load → scroll parents ----------------------------------
// `load` doesn't bubble, but it does fire during the capture phase. One
// root-level capture listener covers every image in the rendered markdown
// (including generated images that finish loading well after the text).
function onImageLoadCapture(e: Event) {
  if ((e.target as HTMLElement | null)?.tagName === 'IMG') {
    emit('image-loaded')
  }
}
watch(
  rootEl,
  (el, prev) => {
    prev?.removeEventListener('load', onImageLoadCapture, true)
    el?.addEventListener('load', onImageLoadCapture, true)
  },
  { flush: 'post' },
)

onBeforeUnmount(() => {
  cleanupTooltips()
  rootEl.value?.removeEventListener('load', onImageLoadCapture, true)
})
</script>

<template>
  <div ref="rootEl" class="message-content">
    <template v-for="(part, pi) in parts" :key="pi">
      <!-- eslint-disable-next-line vue/no-v-html -- sanitized by DOMPurify in renderMarkdown -->
      <div
        v-if="part.type === 'text'"
        class="markdown-content"
        @click="onContentClick"
        v-html="part.html"
      ></div>
      <QuizBlock
        v-else-if="part.type === 'quiz'"
        :quiz="part.quiz"
        :message-id="messageId"
        :quiz-index="part.quizIndex"
        :conversation-name="conversationName"
        :file-name="fileName"
      />
      <MermaidBlock v-else-if="part.type === 'mermaid'" :code="part.code" />
    </template>

    <div v-if="hasPrompts" class="prompts-row">
      <Action
        v-for="label in parsedTokens.visiblePrompts"
        :key="label"
        :label="label"
        @select="emit('select', $event)"
      />
    </div>

    <div v-if="hasActions" class="actions-row">
      <MessageContentAction
        v-for="label in parsedTokens.visibleActions"
        :key="label"
        :label="label"
        @select="emit('select', $event)"
      />
      <MessageContentActionMore
        :actions="parsedTokens.overflowActions"
        @select="emit('select', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.message-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.prompts-row,
.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>

<style>
/*
 * Global (not scoped) so it applies to spans injected via v-html + the
 * `applyWordReveal` walker. Layers cleanly on top of TextFade's color
 * transition: during the 0.25s TextFade the letters are invisible anyway,
 * and once it resolves each word fades in at its staggered delay.
 */
.word-reveal {
  display: inline;
  opacity: 0;
  animation: word-reveal-in 25ms ease-out forwards;
  will-change: opacity;
}
@keyframes word-reveal-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .word-reveal {
    animation: none;
    opacity: 1;
  }
}
</style>
