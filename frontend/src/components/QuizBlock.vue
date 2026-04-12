<template>
  <div class="quiz-block">
    <div class="quiz-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0">
        <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span class="quiz-title">{{ quiz.title }}</span>
    </div>

    <div v-for="(q, qi) in quiz.questions" :key="qi" class="quiz-question">
      <div class="quiz-question-text">{{ qi + 1 }}. {{ q.q }}</div>
      <div class="quiz-options">
        <label
          v-for="(opt, oi) in q.options"
          :key="oi"
          class="quiz-option"
          :class="{
            'selected': selections[qi]?.has(oi),
            'correct': submitted[qi] && q.correct.includes(oi),
            'wrong': submitted[qi] && selections[qi]?.has(oi) && !q.correct.includes(oi),
          }"
        >
          <input
            type="checkbox"
            :checked="selections[qi]?.has(oi)"
            :disabled="submitted[qi]"
            @change="toggleOption(qi, oi)"
          />
          <span class="quiz-option-text">{{ opt }}</span>
          <span v-if="submitted[qi] && q.correct.includes(oi)" class="quiz-check">✓</span>
          <span v-if="submitted[qi] && selections[qi]?.has(oi) && !q.correct.includes(oi)" class="quiz-cross">✗</span>
        </label>
      </div>
      <div class="quiz-actions">
        <button
          v-if="!submitted[qi]"
          class="quiz-submit-btn"
          :disabled="!selections[qi]?.size"
          @click="submitAnswer(qi)"
        >
          Check
        </button>
        <div v-if="submitted[qi]" class="quiz-explanation">
          <span v-if="isCorrect(qi)" class="quiz-result correct">✓ Correct!</span>
          <span v-else class="quiz-result wrong">✗ Incorrect</span>
          <span v-if="q.explanation" class="quiz-explanation-text">{{ q.explanation }}</span>
        </div>
      </div>
    </div>

    <div v-if="allSubmitted" class="quiz-summary">
      <strong>Score: {{ correctCount }}/{{ quiz.questions.length }}</strong>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed } from "vue";

export interface QuizQuestion {
  q: string;
  options: string[];
  correct: number[];
  explanation?: string;
}

export interface QuizData {
  title: string;
  questions: QuizQuestion[];
}

const props = defineProps<{ quiz: QuizData }>();

const selections = reactive<Record<number, Set<number>>>({});
const submitted = reactive<Record<number, boolean>>({});

function toggleOption(qi: number, oi: number) {
  if (!selections[qi]) selections[qi] = new Set();
  if (selections[qi].has(oi)) {
    selections[qi].delete(oi);
  } else {
    selections[qi].add(oi);
  }
}

function submitAnswer(qi: number) {
  submitted[qi] = true;
}

function isCorrect(qi: number): boolean {
  const q = props.quiz.questions[qi];
  const sel = selections[qi] || new Set();
  if (sel.size !== q.correct.length) return false;
  return q.correct.every((c) => sel.has(c));
}

const allSubmitted = computed(() =>
  props.quiz.questions.every((_, i) => submitted[i])
);

const correctCount = computed(() =>
  props.quiz.questions.filter((_, i) => isCorrect(i)).length
);
</script>

<style scoped>
.quiz-block {
  margin: 16px 0;
  border: 1px solid rgba(124, 58, 237, 0.3);
  border-radius: 12px;
  padding: 16px;
  background: rgba(124, 58, 237, 0.06);
}

.quiz-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  color: #c4b5fd;
  font-weight: 600;
  font-size: 15px;
}

.quiz-title {
  flex: 1;
}

.quiz-question {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.quiz-question:last-of-type {
  border-bottom: none;
  margin-bottom: 8px;
  padding-bottom: 0;
}

.quiz-question-text {
  font-weight: 500;
  margin-bottom: 10px;
  color: #e2e8f0;
  font-size: 14px;
  line-height: 1.5;
}

.quiz-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quiz-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.15s;
  font-size: 13px;
  color: #cbd5e1;
}

.quiz-option:hover:not(.correct):not(.wrong) {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.15);
}

.quiz-option.selected:not(.correct):not(.wrong) {
  background: rgba(124, 58, 237, 0.15);
  border-color: rgba(124, 58, 237, 0.4);
  color: #ddd6fe;
}

.quiz-option.correct {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.4);
  color: #86efac;
}

.quiz-option.wrong {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.4);
  color: #fca5a5;
}

.quiz-option input[type="checkbox"] {
  accent-color: #7c3aed;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.quiz-option-text {
  flex: 1;
}

.quiz-check {
  color: #22c55e;
  font-weight: 700;
}

.quiz-cross {
  color: #ef4444;
  font-weight: 700;
}

.quiz-actions {
  margin-top: 10px;
}

.quiz-submit-btn {
  background: #7c3aed;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}

.quiz-submit-btn:hover {
  background: #6d28d9;
}

.quiz-submit-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.quiz-explanation {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.quiz-result.correct {
  color: #22c55e;
  font-weight: 600;
}

.quiz-result.wrong {
  color: #ef4444;
  font-weight: 600;
}

.quiz-explanation-text {
  color: #94a3b8;
}

.quiz-summary {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  text-align: center;
  color: #c4b5fd;
  font-size: 15px;
}
</style>
