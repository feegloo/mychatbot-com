<script setup lang="ts">
/**
 * Renders a parsed assistant message: markdown text interleaved with
 * `[prompt:…]` (Action) and `[action:…]` (MessageContentAction) tokens,
 * with overflow actions collapsed into MessageContentActionMore. Also
 * handles inline quiz / mermaid blocks via async-loaded child components,
 * plus delegated clicks for [source:N] citations, inline images, the
 * [upload] button, and checklist boxes.
 */
import { computed, defineAsyncComponent } from 'vue'
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
</script>

<template>
  <div class="message-content">
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
