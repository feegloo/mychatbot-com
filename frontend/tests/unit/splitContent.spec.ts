import { describe, it, expect, vi } from 'vitest'

// Mock renderMarkdown so tests don't need the full markdown pipeline
vi.mock('../../src/utils/markdown', () => ({
  renderMarkdown: (text: string) => `<p>${text}</p>`,
}))

// Mock QuizBlock import (type-only, no runtime dep)
vi.mock('../../src/components/QuizBlock.vue', () => ({}))

import { splitContent } from '../../src/components/chat/splitContent'

describe('splitContent – quiz parsing', () => {
  const minimalQuizJson = JSON.stringify({
    title: 'Test Quiz',
    multiple: false,
    questions: [
      {
        q: 'What is 1+1?',
        options: ['1', '2', '3'],
        correct: [1],
        explanation: 'Basic arithmetic.',
      },
    ],
  })

  it('extracts a quiz block as a quiz part (not text)', () => {
    const content = `Intro text.\n\n[quiz:${minimalQuizJson}]`
    const parts = splitContent(content)
    const quizParts = parts.filter((p) => p.type === 'quiz')
    expect(quizParts).toHaveLength(1)
  })

  it('preserves quiz title and questions', () => {
    const content = `[quiz:${minimalQuizJson}]`
    const parts = splitContent(content)
    const quizPart = parts.find((p) => p.type === 'quiz')
    expect(quizPart?.type).toBe('quiz')
    if (quizPart?.type === 'quiz') {
      expect(quizPart.quiz.title).toBe('Test Quiz')
      expect(quizPart.quiz.questions).toHaveLength(1)
      expect(quizPart.quiz.questions[0].correct).toEqual([1])
    }
  })

  it('does NOT render the quiz block as raw text', () => {
    const content = `[quiz:${minimalQuizJson}]`
    const parts = splitContent(content)
    const textParts = parts.filter((p) => p.type === 'text')
    for (const tp of textParts) {
      // The quiz JSON should never appear inside a text part
      expect(tp.html).not.toContain('[quiz:')
    }
  })

  it('handles quiz with nested braces in questions', () => {
    const complexJson = JSON.stringify({
      title: 'Complex Quiz',
      multiple: false,
      questions: [
        {
          q: 'Which is correct?',
          options: ['Option A', 'Option B'],
          correct: [0],
        },
      ],
    })
    const content = `[quiz:${complexJson}]`
    const parts = splitContent(content)
    expect(parts.filter((p) => p.type === 'quiz')).toHaveLength(1)
  })

  it('renders surrounding text as text parts', () => {
    const content = `Before.\n\n[quiz:${minimalQuizJson}]\n\nAfter.`
    const parts = splitContent(content)
    expect(parts.some((p) => p.type === 'text' && p.html.includes('Before.'))).toBe(true)
    expect(parts.some((p) => p.type === 'text' && p.html.includes('After.'))).toBe(true)
    expect(parts.filter((p) => p.type === 'quiz')).toHaveLength(1)
  })

  it('falls back to text for a malformed quiz block', () => {
    const content = '[quiz:{bad json}]'
    const parts = splitContent(content)
    // Should not throw; malformed block becomes text
    expect(parts).toBeDefined()
    const quizParts = parts.filter((p) => p.type === 'quiz')
    expect(quizParts).toHaveLength(0)
  })

  it('handles content with no quiz block', () => {
    const content = 'Just some **markdown** text.'
    const parts = splitContent(content)
    expect(parts).toHaveLength(1)
    expect(parts[0].type).toBe('text')
  })
})
