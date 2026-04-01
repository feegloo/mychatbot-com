import { runPythonScript } from "./run-python.js";

export async function answerQuestion(options: {
  conversationId: string;
  collectionName: string;
  question: string;
}) {
  return runPythonScript("answer_question.py", [
    "--conversation-id", options.conversationId,
    "--collection-name", options.collectionName,
    "--question", options.question
  ]);
}
