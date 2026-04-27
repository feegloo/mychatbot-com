import { config } from '../config.js'

export async function answerQuestion(options: {
  conversationId: string
  collectionName: string
  question: string
  chatHistory?: { role: string; content: string; timestamp?: string }[]
  welcomeMessages?: string[]
  imageFilePaths?: string[]
  fileMetadata?: Record<string, any>
  storageDir?: string
  previousSuggestedQuestions?: string[]
  conversationName?: string
  conversationLanguageCode?: string
  conversationLanguageName?: string
  /**
   * Per-conversation internal "idea file" generated at indexing time. When
   * provided, the Python answering pipeline injects it as a structured
   * Section 3a in ANSWER_PROMPT so the LLM has a compounding map of
   * entities/relationships instead of re-deriving them from chunks every turn.
   */
  wikiMessage?: string
  requestId?: string
}) {
  const response = await fetch(`${config.pythonServerUrl}/answer`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.requestId ? { 'X-Request-Id': options.requestId } : {}),
    },
    body: JSON.stringify({
      conversation_id: options.conversationId,
      collection_name: options.collectionName,
      question: options.question,
      chat_history: options.chatHistory || null,
      welcome_messages: options.welcomeMessages || [],
      image_file_paths: options.imageFilePaths || null,
      file_metadata: options.fileMetadata || null,
      storage_dir: options.storageDir || null,
      previous_suggested_questions: options.previousSuggestedQuestions || null,
      conversation_name: options.conversationName || null,
      conversation_language_code: options.conversationLanguageCode || null,
      conversation_language_name: options.conversationLanguageName || null,
      wiki_message: options.wikiMessage || null,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Python server error (${response.status}): ${text}`)
  }

  const parsedJson = await response.json()
  return {
    stdout: JSON.stringify(parsedJson),
    stderr: '',
    parsedJson,
    stdoutLogPath: '',
    stderrLogPath: '',
  }
}
