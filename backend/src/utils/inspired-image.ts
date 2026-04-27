/**
 * Auto-generation of companion images for "inspired" creative-writing answers.
 *
 * When the user asks the model to "write inspired chapter / poem / story / ..."
 * and the LLM produces a substantial piece of text, we roll a coin and — on
 * success — kick off a background image-generation call that paints a picture
 * inspired by the same prompt. The image is then appended to the assistant
 * message's content so the frontend picks it up on its next poll.
 */

// Loose detector: matches phrases like "write inspired chapter",
// "inspired poem like Paulo Coelho", "draft a fairy tale inspired by ...", etc.
// We keep it intentionally permissive so the model's own action labels
// (e.g. "Write inspired chapter like Stephen King ✏️") are covered, while
// still requiring the "inspired" keyword to avoid false positives on
// ordinary Q&A traffic.
const INSPIRED_CREATIVE_RE =
  /\binspired\b[^\n]{0,80}?\b(chapter|large\s+chapter|poem|poet|story|stories|tale|fairy|song|lyric|essay|monologue|scene|parable|short\s+story)\b|\b(chapter|large\s+chapter|poem|poet|story|tale|fairy|song|lyric|essay|monologue|scene|parable)s?\b[^\n]{0,80}?\binspired\b/i

// Only auto-generate when the answer is clearly a "large chunk of text".
// Creative chapters/poems usually blow well past this threshold; short
// clarifying answers stay image-free.
const MIN_ANSWER_LENGTH = 600

export function isInspiredCreativeQuestion(question: string): boolean {
  return INSPIRED_CREATIVE_RE.test(question)
}

export function shouldAutoGenerateImage(
  question: string,
  answer: string,
  probability = 0.5,
  random: () => number = Math.random,
): boolean {
  if (!isInspiredCreativeQuestion(question)) return false
  if ((answer || '').length < MIN_ANSWER_LENGTH) return false
  return random() < probability
}

/**
 * When a reusable image is available for an inspired-creative answer we
 * prefer borrowing it (saves an OpenAI image-gen call) over generating a
 * fresh one. Occasionally we still generate a new image so the gallery
 * keeps expanding — the default split matches the spec the feature was
 * scoped to: 70% reuse / 30% generate new.
 */
export function shouldReuseImage(
  probability = 0.7,
  random: () => number = Math.random,
): boolean {
  return random() < probability
}

/**
 * Gate for "should we even ask the reusable-image service?". We only want
 * to consult it for questions that would otherwise be eligible for the
 * auto-image branch — i.e. creative-writing prompts with a substantial
 * answer. This mirrors the guards inside ``shouldAutoGenerateImage`` but
 * without the probability coin flip: the reuse decision runs first and
 * the coin flip moves down into ``shouldReuseImage`` /
 * ``shouldAutoGenerateImage`` depending on whether a match was found.
 */
export function isEligibleForImageAugmentation(
  question: string,
  answer: string,
): boolean {
  if (!isInspiredCreativeQuestion(question)) return false
  if ((answer || '').length < MIN_ANSWER_LENGTH) return false
  return true
}

// Keep the prompt payload bounded so the Python side doesn't choke on huge
// inputs and OpenAI stays within context limits.
const MAX_ANSWER_SNIPPET = 1500

export function buildAutoImageQuestion(userQuestion: string, answer: string): string {
  const trimmed = (answer || '').slice(0, MAX_ANSWER_SNIPPET).trim()
  if (!trimmed) return userQuestion
  return `${userQuestion}\n\n---\n\n${trimmed}`
}

export type ImageCitation = {
  fileName: string
  chunkId: string
  text: string
  section?: string | null
  page?: number | null
}

export type AutoImageResult = {
  fileName: string
  imageUrl: string
  imageTitle: string
  imagePrompt: string
  imageSources: ImageCitation[]
}

/**
 * Compose the markdown + HTML snippet that gets appended to the assistant
 * message. Mirrors the look of the dedicated /generate-image route
 * (image + caption with quoted title + source markers), and tacks on a
 * small "generated image" sublabel so users know it was auto-produced.
 *
 * Source markers are offset by the number of citations already present in
 * the original answer so the `[N]` indices line up with the combined
 * citations array the frontend receives.
 */
export function renderAutoImageMarkdown(
  result: AutoImageResult,
  originalCitationsCount: number,
): string {
  const markers = result.imageSources.length
    ? ' ' +
      result.imageSources
        .map((_, i) => `[${originalCitationsCount + i + 1}]`)
        .join('')
    : ''
  return (
    `\n\n![${result.imageTitle}](${result.imageUrl})\n` +
    `<p class="image-caption">"${result.imageTitle}"${markers}</p>\n`
  )
}

/**
 * Merge the existing assistant citations (plain array) with the new image
 * sources into a hybrid object that also carries image metadata for the
 * chat-history builder and downstream consumers.
 */
export function mergeCitationsWithImage(
  originalCitations: unknown,
  result: AutoImageResult,
): {
  citations: unknown[]
  _imageSources: ImageCitation[]
  _generatedImageDescription: string
  _autoGeneratedImage: true
} {
  const base = Array.isArray(originalCitations) ? originalCitations : []
  return {
    citations: base,
    _imageSources: result.imageSources,
    _generatedImageDescription: result.imagePrompt,
    _autoGeneratedImage: true,
  }
}

/**
 * Shape of a reused image appended to an answer. The URL already points to
 * the *source* conversation's storage endpoint — images are served
 * publicly from /api/storage/:id/:file so cross-conversation linking works
 * without copying the asset.
 */
export type ReusedImage = {
  imageUrl: string
  imageTitle: string
  imageDescription: string
  sourceConversationId: string
  sourceImageId: string
}

/**
 * Build the same centered-caption markdown used by freshly generated
 * images, so the frontend treats reused images identically (including
 * the image-caption CSS that centers the title below the <img>).
 */
export function renderReusedImageMarkdown(reused: ReusedImage): string {
  return (
    `\n\n![${reused.imageTitle}](${reused.imageUrl})\n` +
    `<p class="image-caption">"${reused.imageTitle}"</p>\n`
  )
}

/**
 * Annotate citations with reuse metadata. The reused image itself carries
 * no fresh citations — it was grounded in its original conversation's
 * chunks — so we only stamp the description (for the chat-history
 * context builder) and a flag that makes future debugging easier.
 */
export function mergeCitationsWithReusedImage(
  originalCitations: unknown,
  reused: ReusedImage,
): {
  citations: unknown[]
  _generatedImageDescription: string
  _reusedImage: { sourceConversationId: string; sourceImageId: string }
} {
  const base = Array.isArray(originalCitations) ? originalCitations : []
  return {
    citations: base,
    _generatedImageDescription: reused.imageDescription,
    _reusedImage: {
      sourceConversationId: reused.sourceConversationId,
      sourceImageId: reused.sourceImageId,
    },
  }
}
