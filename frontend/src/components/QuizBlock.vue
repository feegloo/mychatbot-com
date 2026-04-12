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
            class="quiz-checkbox"
            @change="toggleOption(qi, oi)"
          />
          <span class="quiz-checkbox-custom"></span>
          <span class="quiz-option-text">{{ opt }}</span>
        </label>
      </div>
      <div v-if="submitted[qi] && q.explanation" class="quiz-explanation">
        <span class="quiz-explanation-text">{{ q.explanation }}</span>
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
  if (submitted[qi]) return;
  if (!selections[qi]) selections[qi] = new Set();
  if (selections[qi].has(oi)) {
    selections[qi].delete(oi);
  } else {
    selections[qi].add(oi);
  }
  // Auto-submit once at least one option is selected
  if (selections[qi].size) {
    submitted[qi] = true;
  }
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
  position: relative;
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

.quiz-option input[type="checkbox"].quiz-checkbox {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

.quiz-checkbox-custom {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  border: 2px solid rgba(255, 255, 255, 0.25);
  background: transparent;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

/* Checked state (before submission) */
.quiz-checkbox:checked ~ .quiz-checkbox-custom {
  background: #7c3aed;
  border-color: #7c3aed;
}

.quiz-checkbox:checked ~ .quiz-checkbox-custom::after {
  content: '✓';
  color: white;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

/* Correct answer after submission */
.quiz-option.correct .quiz-checkbox-custom {
  background: #22c55e;
  border-color: #22c55e;
}

.quiz-option.correct .quiz-checkbox-custom::after {
  content: '✓';
  color: white;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

/* Wrong answer after submission */
.quiz-option.wrong .quiz-checkbox-custom {
  background: #ef4444;
  border-color: #ef4444;
}

.quiz-option.wrong .quiz-checkbox-custom::after {
  content: '✗';
  color: white;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}

/* Unselected correct option: show green outline but no fill */
.quiz-option.correct .quiz-checkbox:not(:checked) ~ .quiz-checkbox-custom {
  background: transparent;
  border-color: #22c55e;
}

.quiz-option.correct .quiz-checkbox:not(:checked) ~ .quiz-checkbox-custom::after {
  content: '';
}

.quiz-option-text {
  flex: 1;
}

.quiz-explanation {
  margin-top: 10px;
  font-size: 13px;
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
