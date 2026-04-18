<template>
  <div class="quiz-block">
    <div class="quiz-header">
      <span class="quiz-title">{{ quiz.title }} - Quiz 🧠</span>
      <button class="quiz-download-btn" title="Download PDF" @click="downloadPdf">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        PDF
      </button>
    </div>

    <div class="quiz-type-badge">{{ isMultiple ? '☑ Multiple choice' : '○ Single choice' }}</div>
    <button class="quiz-restart-btn" @click="restartQuiz">⟲ Restart quiz</button>

    <div v-for="(q, qi) in quiz.questions" :key="qi" class="quiz-question">
      <div class="quiz-question-text">{{ qi + 1 }}. {{ q.q }}</div>
      <div class="quiz-options">
        <!-- SINGLE CHOICE: radio-style -->
        <template v-if="!isMultiple">
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
              type="radio"
              :name="`quiz-${messageId}-${quizIndex}-q${qi}`"
              :checked="selections[qi]?.has(oi)"
              class="quiz-radio"
              @click="toggleSingle(qi, oi)"
            />
            <span class="quiz-radio-custom"></span>
            <span class="quiz-option-text"><span class="quiz-variant-label">{{ variantLetter(oi) }}.</span> {{ opt }}</span>
          </label>
        </template>

        <!-- MULTIPLE CHOICE: checkbox-style -->
        <template v-else>
          <label
            v-for="(opt, oi) in q.options"
            :key="oi"
            class="quiz-option"
            :class="multiOptionClass(qi, oi)"
          >
            <input
              type="checkbox"
              :checked="selections[qi]?.has(oi)"
              class="quiz-checkbox"
              @change="toggleMulti(qi, oi)"
            />
            <span class="quiz-checkbox-custom"></span>
            <span class="quiz-option-text"><span class="quiz-variant-label">{{ variantLetter(oi) }}.</span> {{ opt }}</span>
          </label>
        </template>
      </div>
      <div v-if="showExplanation(qi) && q.explanation" class="quiz-explanation">
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
import { ensureFontsLoaded, registerFonts, PDF_FONT } from "../utils/pdfFonts";

export interface QuizQuestion {
  q: string;
  options: string[];
  correct: number[];
  explanation?: string;
}

export interface QuizData {
  title: string;
  multiple?: boolean;
  questions: QuizQuestion[];
}

const props = defineProps<{
  quiz: QuizData;
  messageId?: string;
  quizIndex?: number;
  conversationName?: string;
  fileName?: string;
}>();

const isMultiple = computed(() => props.quiz.multiple === true);

function variantLetter(index: number): string {
  return String.fromCharCode(65 + index);
}

const selections = reactive<Record<number, Set<number>>>({});
const submitted = reactive<Record<number, boolean>>({});
// For multiple choice: track which individual options were marked wrong
const wrongOptions = reactive<Record<number, Set<number>>>({});

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
  const wrongData: Record<number, number[]> = {};
  for (const [qi, opts] of Object.entries(wrongOptions)) {
    wrongData[Number(qi)] = [...opts];
  }
  setData(key, {
    selections: data,
    submitted: { ...submitted },
    multiple: isMultiple.value,
    wrongOptions: wrongData,
  });
}

function loadState() {
  const key = storageKey();
  if (!key) return;
  try {
    const state = getData<{
      selections: Record<number, number[]>;
      submitted: Record<number, boolean>;
      multiple?: boolean;
      wrongOptions?: Record<number, number[]>;
    }>(key);
    if (!state) return;
    for (const [qi, opts] of Object.entries(state.selections ?? {})) {
      selections[Number(qi)] = new Set(opts);
    }
    Object.assign(submitted, state.submitted ?? {});
    if (state.wrongOptions) {
      for (const [qi, opts] of Object.entries(state.wrongOptions)) {
        wrongOptions[Number(qi)] = new Set(opts);
      }
    }
  } catch { /* ignore corrupt data */ }
}

onMounted(loadState);

// ---------- SINGLE CHOICE (radio) ----------
function toggleSingle(qi: number, oi: number) {
  if (!selections[qi]) selections[qi] = new Set();

  if (selections[qi].has(oi)) {
    // Unclick — deselect
    selections[qi].clear();
    submitted[qi] = false;
  } else {
    // Select new option (clear previous)
    selections[qi].clear();
    submitted[qi] = false;
    selections[qi].add(oi);
    submitted[qi] = true;
  }
  saveState();
}

// ---------- MULTIPLE CHOICE (checkbox) ----------
function toggleMulti(qi: number, oi: number) {
  const q = props.quiz.questions[qi];
  if (!selections[qi]) selections[qi] = new Set();
  if (!wrongOptions[qi]) wrongOptions[qi] = new Set();

  if (selections[qi].has(oi)) {
    // Uncheck
    selections[qi].delete(oi);
    wrongOptions[qi].delete(oi);
    // If a wrong option was unchecked, and no wrong options remain, reset submitted state
    // to allow continued selection
    if (wrongOptions[qi].size === 0) {
      submitted[qi] = false;
    }
  } else {
    // Check
    selections[qi].add(oi);

    // If this option is wrong, mark it immediately
    if (!q.correct.includes(oi)) {
      wrongOptions[qi].add(oi);
      submitted[qi] = true; // lock: show wrong immediately
    } else {
      // Correct option selected — check if all correct answers are now selected
      const allCorrectSelected = q.correct.every(c => selections[qi].has(c));
      if (allCorrectSelected && wrongOptions[qi].size === 0) {
        submitted[qi] = true; // all correct found, show success
      }
    }
  }
  saveState();
}

function multiOptionClass(qi: number, oi: number) {
  const q = props.quiz.questions[qi];
  const sel = selections[qi] || new Set();
  const wrong = wrongOptions[qi] || new Set();
  const isSelected = sel.has(oi);
  const isSubmitted = submitted[qi];

  return {
    'selected': isSelected && !isSubmitted,
    'correct': isSubmitted && q.correct.includes(oi) && isSelected,
    'wrong': wrong.has(oi),
    'submitted': isSubmitted,
    // Show green outline on unselected correct options only when fully resolved
    'correct-reveal': isSubmitted && q.correct.includes(oi) && !isSelected,
  };
}

function showExplanation(qi: number): boolean {
  return !!submitted[qi];
}

function isCorrect(qi: number): boolean {
  const q = props.quiz.questions[qi];
  const sel = selections[qi] || new Set();
  const wrong = wrongOptions[qi] || new Set();
  if (wrong.size > 0) return false;
  if (sel.size !== q.correct.length) return false;
  return q.correct.every((c) => sel.has(c));
}

const allSubmitted = computed(() =>
  props.quiz.questions.every((_, i) => submitted[i])
);

function restartQuiz() {
  for (let i = 0; i < props.quiz.questions.length; i++) {
    selections[i] = new Set();
    submitted[i] = false;
    wrongOptions[i] = new Set();
  }
  saveState();
}

const correctCount = computed(() =>
  props.quiz.questions.filter((_, i) => isCorrect(i)).length
);

async function downloadPdf() {
  const [{ default: jsPDF }] = await Promise.all([import("jspdf"), ensureFontsLoaded()]);
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
  doc.setFontSize(15);
  doc.setTextColor(0, 0, 0);
  doc.text(`${props.quiz.title} - Quiz \uD83E\uDDE0`, marginLeft, y);
  y += 7;

  // Quiz type subtitle
  doc.setFont(PDF_FONT, "normal");
  doc.setFontSize(9);
  doc.setTextColor(100, 100, 100);
  const typeLabel = isMultiple.value
    ? "Multiple choice — select all correct answers"
    : "Single choice — select one correct answer";
  doc.text(typeLabel, marginLeft, y);
  y += 6;

  // Name line
  doc.setFont(PDF_FONT, "normal");
  doc.setFontSize(10);
  doc.setTextColor(0, 0, 0);
  doc.text("Name: ___________________________________    Date: _______________", marginLeft, y);
  y += 9;

  // Questions
  for (let qi = 0; qi < props.quiz.questions.length; qi++) {
    const q = props.quiz.questions[qi];

    // Estimate space needed for question header + at least one option
    checkNewPage(30);

    // Question text
    doc.setFont(PDF_FONT, "bold");
    doc.setFontSize(10);
    const questionText = `${qi + 1}. ${q.q}`;
    const questionLines = doc.splitTextToSize(questionText, contentWidth);
    doc.text(questionLines, marginLeft, y);
    y += questionLines.length * 4.8 + 2;

    // Options
    doc.setFont(PDF_FONT, "normal");
    doc.setFontSize(9.5);
    for (let oi = 0; oi < q.options.length; oi++) {
      const letter = variantLetter(oi);
      const optText = `${letter}. ${q.options[oi]}`;
      const optLines = doc.splitTextToSize(optText, contentWidth - 12);

      checkNewPage(optLines.length * 4.5 + 3);

      // Draw radio circle (single choice) or checkbox (multiple choice)
      const boxX = marginLeft + 2;
      const boxY = y - 2.8;
      const isChecked = selections[qi]?.has(oi);
      const isWrong = isChecked && !q.correct.includes(oi);
      doc.setDrawColor(100, 100, 100);
      doc.setLineWidth(0.4);
      if (isMultiple.value) {
        doc.rect(boxX, boxY, 3, 3);
        if (isChecked) {
          doc.setDrawColor(0, 0, 0);
          doc.setLineWidth(0.6);
          if (isWrong) {
            // Draw X inside box for wrong answer
            doc.line(boxX + 0.4, boxY + 0.4, boxX + 2.6, boxY + 2.6);
            doc.line(boxX + 2.6, boxY + 0.4, boxX + 0.4, boxY + 2.6);
          } else {
            // Draw checkmark inside box for correct answer
            doc.line(boxX + 0.5, boxY + 1.5, boxX + 1.2, boxY + 2.4);
            doc.line(boxX + 1.2, boxY + 2.4, boxX + 2.5, boxY + 0.6);
          }
          doc.setLineWidth(0.4);
        }
      } else {
        doc.circle(boxX + 1.5, boxY + 1.5, 1.5);
        if (isChecked) {
          if (isWrong) {
            // Draw X inside circle for wrong answer
            doc.setDrawColor(0, 0, 0);
            doc.setLineWidth(0.6);
            doc.line(boxX + 0.4, boxY + 0.4, boxX + 2.6, boxY + 2.6);
            doc.line(boxX + 2.6, boxY + 0.4, boxX + 0.4, boxY + 2.6);
            doc.setLineWidth(0.4);
          } else {
            // Draw filled inner circle for correct answer
            doc.setFillColor(0, 0, 0);
            doc.circle(boxX + 1.5, boxY + 1.5, 0.85, 'F');
          }
        }
      }

      // Option text
      doc.text(optLines, marginLeft + 9, y);
      y += optLines.length * 4.5 + 1.5;
    }

    // Explanation (if question was submitted and has explanation)
    if (showExplanation(qi) && q.explanation) {
      checkNewPage(10);
      doc.setFont(PDF_FONT, "italic");
      doc.setFontSize(8.5);
      doc.setTextColor(80, 80, 80);
      const expLines = doc.splitTextToSize(q.explanation, contentWidth - 4);
      doc.text(expLines, marginLeft + 2, y);
      y += expLines.length * 3.8 + 1.5;
      doc.setTextColor(0, 0, 0);
    }

    y += 3; // Space between questions
  }

  // Score summary (if all questions answered)
  if (allSubmitted.value) {
    checkNewPage(12);
    doc.setFont(PDF_FONT, "bold");
    doc.setFontSize(11);
    doc.setTextColor(0, 0, 0);
    doc.text(`Score: ${correctCount.value}/${props.quiz.questions.length}`, marginLeft, y);
    y += 8;
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

  // Add watermark on every page
  const totalPages = doc.getNumberOfPages();
  for (let p = 1; p <= totalPages; p++) {
    doc.setPage(p);
    const pw = doc.internal.pageSize.getWidth();
    const ph = doc.internal.pageSize.getHeight();
    doc.setFont(PDF_FONT, "bold");
    doc.setFontSize(8);
    const prefix = "created with ";
    const link = "chatrag.app";
    doc.setFont(PDF_FONT, "normal");
    const prefixWidth = doc.getTextWidth(prefix);
    const linkWidth = doc.getTextWidth(link);
    const totalWidth = prefixWidth + linkWidth;
    const wmX = pw - 12 - totalWidth;
    const wmY = ph - 8;
    doc.setTextColor(0, 0, 0);
    doc.setGState(new (doc as any).GState({ opacity: 0.35 }));
    doc.text(prefix, wmX, wmY);
    doc.setTextColor(70, 130, 220);
    doc.textWithLink(link, wmX + prefixWidth, wmY, { url: "https://chatrag.app" });
    doc.setGState(new (doc as any).GState({ opacity: 1 }));
  }

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
  margin-bottom: 8px;
  color: #c4b5fd;
  font-weight: 600;
  font-size: 15px;
}

.quiz-title {
  flex: 1;
}

.quiz-type-badge {
  font-size: 12px;
  color: #a78bfa;
  margin-bottom: 6px;
  opacity: 0.8;
}

.quiz-restart-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.10);
  background: rgba(255, 255, 255, 0.04);
  color: #a78bfa;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 14px;
}

@media (hover: hover) {
  .quiz-restart-btn:hover {
    background: rgba(124, 58, 237, 0.15);
    border-color: rgba(124, 58, 237, 0.35);
  }
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
  .quiz-option:hover:not(.correct):not(.wrong):not(.correct-reveal) {
    background: rgba(15, 23, 42, 0.65);
    border-color: rgba(255, 255, 255, 0.12);
  }
}
.quiz-option:active:not(.correct):not(.wrong):not(.correct-reveal) {
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

.quiz-option.correct-reveal {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.25);
  color: #86efac;
}

.quiz-option.wrong {
  background: rgba(239, 68, 68, 0.12);
  border-color: rgba(239, 68, 68, 0.4);
  color: #fca5a5;
  cursor: pointer;
}

.quiz-option.submitted:not(.correct):not(.wrong):not(.correct-reveal) {
  cursor: pointer;
}

/* ---- Hidden native inputs ---- */
.quiz-option input[type="checkbox"].quiz-checkbox,
.quiz-option input[type="radio"].quiz-radio {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

/* ---- CHECKBOX custom (multiple choice) ---- */
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

.quiz-option.correct-reveal .quiz-checkbox-custom {
  background: transparent;
  border-color: #22c55e;
}

.quiz-option.correct-reveal .quiz-checkbox-custom::after {
  content: '';
}

.quiz-option.correct .quiz-checkbox:not(:checked) ~ .quiz-checkbox-custom {
  background: transparent;
  border-color: #22c55e;
}

.quiz-option.correct .quiz-checkbox:not(:checked) ~ .quiz-checkbox-custom::after {
  content: '';
}

/* ---- RADIO custom (single choice) ---- */
.quiz-radio-custom {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.25);
  background: transparent;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.quiz-radio:checked ~ .quiz-radio-custom {
  border-color: #7c3aed;
}

.quiz-radio:checked ~ .quiz-radio-custom::after {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7c3aed;
}

.quiz-option.correct .quiz-radio-custom {
  border-color: #22c55e;
}

.quiz-option.correct .quiz-radio-custom::after {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
}

.quiz-option.wrong .quiz-radio-custom {
  border-color: #ef4444;
}

.quiz-option.wrong .quiz-radio-custom::after {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
}

.quiz-option.correct .quiz-radio:not(:checked) ~ .quiz-radio-custom {
  border-color: #22c55e;
}

.quiz-option.correct .quiz-radio:not(:checked) ~ .quiz-radio-custom::after {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: transparent;
  border: 2px solid #22c55e;
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
