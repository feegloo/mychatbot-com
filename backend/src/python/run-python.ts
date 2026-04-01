import { spawn } from "node:child_process";
import path from "node:path";
import { config } from "../config.js";

export type PythonCommandResult = {
  stdout: string;
  stderr: string;
  parsedJson?: any;
};

export async function runPythonScript(scriptName: string, args: string[]): Promise<PythonCommandResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(config.pythonBin, [path.join(config.pythonProjectRoot, scriptName), ...args], {
      cwd: config.pythonProjectRoot,
      env: {
        ...process.env,
        OPENAI_API_KEY: config.openAiApiKey,
        OPENAI_CHAT_MODEL: config.openAiChatModel,
        OPENAI_EMBEDDING_MODEL: config.openAiEmbeddingModel,
        CHROMA_MODE: config.chromaMode,
        CHROMA_HTTP_HOST: config.chromaHttpHost,
        CHROMA_PERSIST_DIR: config.chromaPersistDir
      }
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("close", (code) => {
      if (code === 0) {
        let parsedJson: any;
        try {
          parsedJson = JSON.parse(stdout.trim().split("\n").slice(-1)[0]);
        } catch {
          parsedJson = undefined;
        }

        resolve({ stdout, stderr, parsedJson });
      } else {
        reject(new Error(stderr || stdout || `Python process failed with code ${code}`));
      }
    });
  });
}
