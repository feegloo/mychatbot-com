<template>
  <div class="quiz-block">
    <div class="quiz-header">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0">
        <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span class="quiz-title">{{ quiz.title }}</span>
      <button class="quiz-download-btn" title="Download PDF" @click="downloadPdf">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        PDF
      </button>
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
            'submitted': submitted[qi],
          }"
        >
          <input
            type="checkbox"
            :checked="selections[qi]?.has(oi)"
            class="quiz-checkbox"
            @change="toggleOption(qi, oi)"
          />
          <span class="quiz-checkbox-custom"></span>
          <span class="quiz-option-text"><span class="quiz-variant-label">{{ variantLetter(oi) }}.</span> {{ opt }}</span>
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
import { reactive, computed, onMounted } from "vue";
import { getData, setData } from "../utils/localData";
import jsPDF from "jspdf";
import { ensureFontsLoaded, registerFonts, PDF_FONT } from "../utils/pdfFonts";

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

const props = defineProps<{
  quiz: QuizData;
  messageId?: string;
  quizIndex?: number;
  conversationName?: string;
  fileName?: string;
}>();

function variantLetter(index: number): string {
  return String.fromCharCode(65 + index); // A, B, C, D, ...
}

const selections = reactive<Record<number, Set<number>>>({});
const submitted = reactive<Record<number, boolean>>({});

function storageKey(): string | null {
  return props.messageId ? `quiz:${props.messageId}:${props.quizIndex ?? 0}` : null;
}

function saveState() {
  const key = storageKey();
  if (!key) return;
  const data: Record<number, number[]> = {};
  for (const [qi, opts] of Object.entries(selections)) {
    data[Number(qi)] = [...opts];
  }
  setData(key, { selections: data, submitted: { ...submitted } });
}

function loadState() {
  const key = storageKey();
  if (!key) return;
  try {
    const state = getData<{ selections: Record<number, number[]>; submitted: Record<number, boolean> }>(key);
    if (!state) return;
    for (const [qi, opts] of Object.entries(state.selections ?? {})) {
      selections[Number(qi)] = new Set(opts);
    }
    Object.assign(submitted, state.submitted ?? {});
  } catch { /* ignore corrupt data */ }
}

onMounted(loadState);

function toggleOption(qi: number, oi: number) {
  if (!selections[qi]) selections[qi] = new Set();
  if (selections[qi].has(oi)) {
    selections[qi].delete(oi);
  } else {
    // If already submitted, reset first (clear previous selection)
    if (submitted[qi]) {
      selections[qi].clear();
      submitted[qi] = false;
    }
    selections[qi].add(oi);
  }
  // Auto-submit once at least one option is selected, reset if none
  if (selections[qi].size) {
    submitted[qi] = true;
  } else {
    submitted[qi] = false;
  }
  saveState();
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

async function downloadPdf() {
  await ensureFontsLoaded();
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  registerFonts(doc);
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const marginLeft = 20;
  const marginRight = 20;
  const contentWidth = pageWidth - marginLeft - marginRight;
  let y = 20;

  const checkNewPage = (needed: number) => {
    if (y + needed > pageHeight - 20) {
      doc.addPage();
      y = 20;
    }
  };

  // Title
  doc.setFont(PDF_FONT, "bold");
  doc.setFontSize(18);
  doc.setTextColor(0, 0, 0);
  doc.text(props.quiz.title, marginLeft, y);
  y += 12;

  // Thin separator
  doc.setDrawColor(180, 180, 180);
  doc.setLineWidth(0.3);
  doc.line(marginLeft, y, pageWidth - marginRight, y);
  y += 8;

  // Name line
  doc.setFont(PDF_FONT, "normal");
  doc.setFontSize(11);
  doc.text("Name: ___________________________________    Date: _______________", marginLeft, y);
  y += 12;

  // Questions
  for (let qi = 0; qi < props.quiz.questions.length; qi++) {
    const q = props.quiz.questions[qi];

    // Estimate space needed for question header + at least one option
    checkNewPage(30);

    // Question text
    doc.setFont(PDF_FONT, "bold");
    doc.setFontSize(11);
    const questionText = `${qi + 1}. ${q.q}`;
    const questionLines = doc.splitTextToSize(questionText, contentWidth);
    doc.text(questionLines, marginLeft, y);
    y += questionLines.length * 5.5 + 3;

    // Options
    doc.setFont(PDF_FONT, "normal");
    doc.setFontSize(10.5);
    for (let oi = 0; oi < q.options.length; oi++) {
      const letter = variantLetter(oi);
      const optText = `${letter}. ${q.options[oi]}`;
      const optLines = doc.splitTextToSize(optText, contentWidth - 12);

      checkNewPage(optLines.length * 5 + 4);

      // Empty checkbox
      const boxX = marginLeft + 2;
      const boxY = y - 3.2;
      doc.setDrawColor(100, 100, 100);
      doc.setLineWidth(0.4);
      doc.rect(boxX, boxY, 3.5, 3.5);

      // Option text
      doc.text(optLines, marginLeft + 9, y);
      y += optLines.length * 5 + 2;
    }

    y += 5; // Space between questions
  }

  // Build filename
  const nameParts: string[] = ["quiz"];
  if (props.fileName) {
    nameParts.push(props.fileName.replace(/\.[^.]+$/, ""));
  }
  if (props.conversationName) {
    nameParts.push(props.conversationName);
  }
  const safeName = nameParts
    .join("-")
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .slice(0, 100);

  doc.save(`${safeName}.pdf`);
}
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

.quiz-download-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  color: #c4b5fd;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

@media (hover: hover) {
  .quiz-download-btn:hover {
    background: rgba(124, 58, 237, 0.18);
    border-color: rgba(124, 58, 237, 0.4);
  }
}

.quiz-variant-label {
  font-weight: 600;
  margin-right: 2px;
  color: #a78bfa;
}

.quiz-question {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.quiz-question:last-child,
.quiz-question:has(+ .quiz-summary) {
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
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(15, 23, 42, 0.45);
  cursor: pointer;
  transition: all 0.15s;
  font-size: 13px;
  color: #cbd5e1;
  position: relative;
}

@media (hover: hover) {
  .quiz-option:hover:not(.correct):not(.wrong) {
    background: rgba(15, 23, 42, 0.65);
    border-color: rgba(255, 255, 255, 0.12);
  }
}
.quiz-option:active:not(.correct):not(.wrong) {
  background: rgba(15, 23, 42, 0.65);
  border-color: rgba(255, 255, 255, 0.12);
}

.quiz-option.selected:not(.correct):not(.wrong) {
  background: rgba(124, 58, 237, 0.12);
  border-color: rgba(124, 58, 237, 0.3);
  color: #ddd6fe;
}

.quiz-option.correct {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.4);
  color: #86efac;
  cursor: pointer;
}

.quiz-option.wrong {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.4);
  color: #fca5a5;
  cursor: pointer;
}

.quiz-option.submitted:not(.correct):not(.wrong) {
  cursor: pointer;
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
