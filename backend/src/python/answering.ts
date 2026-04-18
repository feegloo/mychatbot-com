import { config } from "../config.js";

export async function answerQuestion(options: {
  conversationId: string;
  collectionName: string;
  question: string;
  chatHistory?: { role: string; content: string }[];
  welcomeMessages?: string[];
  imageFilePaths?: string[];
  fileMetadata?: Record<string, any>;
  storageDir?: string;
  previousSuggestedQuestions?: string[];
}) {
  const response = await fetch(`${config.pythonServerUrl}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Python server error (${response.status}): ${text}`);
  }

  const parsedJson = await response.json();
  return {
    stdout: JSON.stringify(parsedJson),
    stderr: "",
    parsedJson,
    stdoutLogPath: "",
    stderrLogPath: "",
  };
}