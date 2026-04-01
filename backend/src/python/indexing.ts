import { runPythonScript } from "./run-python.js";

export async function indexConversation(options: {
  conversationId: string;
  collectionName: string;
  files: string[];
  mode: "script" | "notebook";
}) {
  const args = [
    "--conversation-id", options.conversationId,
    "--collection-name", options.collectionName
  ];

  for (const file of options.files) {
    args.push("--file", file);
  }

  if (options.mode === "notebook") {
    return runPythonScript("run_notebook_indexer.py", args);
  }

  return runPythonScript("index_documents.py", args);
}
