import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import fsp from "node:fs/promises";
import { config } from "../config.js";

export type PythonCommandResult = {
  stdout: string;
  stderr: string;
  parsedJson?: any;
  stdoutLogPath: string;
  stderrLogPath: string;
};

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

async function ensureDir(dir: string) {
  await fsp.mkdir(dir, { recursive: true });
}

export async function runPythonScript(
  scriptName: string,
  args: string[],
  context?: { conversationId?: string; purpose?: string }
): Promise<PythonCommandResult> {
  const conversationId = context?.conversationId || "unknown";
  const purpose = context?.purpose || "python";
  const logsDir = path.join(config.logsRoot, conversationId);

  await ensureDir(logsDir);

  const baseName = `${timestamp()}_${purpose}_${path.basename(scriptName, ".py")}`;
  const stdoutLogPath = path.join(logsDir, `${baseName}.stdout.log`);
  const stderrLogPath = path.join(logsDir, `${baseName}.stderr.log`);

  const stdoutStream = fs.createWriteStream(stdoutLogPath, { flags: "a" });
  const stderrStream = fs.createWriteStream(stderrLogPath, { flags: "a" });

  return new Promise((resolve, reject) => {
    const fullScriptPath = path.join(config.pythonProjectRoot, scriptName);

    console.log("[python] starting", {
      scriptName,
      fullScriptPath,
      args,
      conversationId,
      purpose
    });

    stdoutStream.write(`START ${new Date().toISOString()}\n`);
    stdoutStream.write(`SCRIPT ${fullScriptPath}\n`);
    stdoutStream.write(`ARGS ${JSON.stringify(args)}\n\n`);

    stderrStream.write(`START ${new Date().toISOString()}\n`);
    stderrStream.write(`SCRIPT ${fullScriptPath}\n`);
    stderrStream.write(`ARGS ${JSON.stringify(args)}\n\n`);

    const child = spawn(config.pythonBin, [fullScriptPath, ...args], {
      cwd: config.pythonProjectRoot,
      env: {
        ...process.env,
        OPENAI_API_KEY: config.openAiApiKey,
        OPENAI_CHAT_MODEL: config.openAiChatModel,
        OPENAI_EMBEDDING_MODEL: config.openAiEmbeddingModel,
        CHROMA_MODE: config.chromaMode,
        CHROMA_HTTP_HOST: config.chromaHttpHost,
        CHROMA_PERSIST_DIR: config.chromaPersistDir,
        CHROMA_API_KEY: config.chromaApiKey,
        CHROMA_TENANT: config.chromaTenant,
        CHROMA_DATABASE: config.chromaDatabase
      }
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      const text = chunk.toString();
      stdout += text;
      stdoutStream.write(text);
      console.log(`[python:${path.basename(scriptName)}:stdout] ${text.trimEnd()}`);
    });

    child.stderr.on("data", (chunk) => {
      const text = chunk.toString();
      stderr += text;
      stderrStream.write(text);
      console.error(`[python:${path.basename(scriptName)}:stderr] ${text.trimEnd()}`);
    });

    child.on("error", (error) => {
      const text = `PROCESS_ERROR ${error.stack || error.message}\n`;
      stderr += text;
      stderrStream.write(text);
      stderrStream.end();
      stdoutStream.end();
      reject(
        new Error(
          `Failed to start Python process: ${error.message}\n` +
          `stderr log: ${stderrLogPath}`
        )
      );
    });

    child.on("close", (code) => {
      stdoutStream.write(`\nEND ${new Date().toISOString()} code=${code}\n`);
      stderrStream.write(`\nEND ${new Date().toISOString()} code=${code}\n`);
      stdoutStream.end();
      stderrStream.end();

      console.log("[python] finished", {
        scriptName,
        code,
        stdoutLogPath,
        stderrLogPath
      });

      if (code === 0) {
        let parsedJson: any;
        try {
          parsedJson = JSON.parse(stdout.trim().split("\n").slice(-1)[0]);
        } catch {
          parsedJson = undefined;
        }

        resolve({
          stdout,
          stderr,
          parsedJson,
          stdoutLogPath,
          stderrLogPath
        });
      } else {
        reject(
          new Error(
            [
              `Python process failed with code ${code}`,
              `script: ${scriptName}`,
              `stdout log: ${stdoutLogPath}`,
              `stderr log: ${stderrLogPath}`,
              stderr || stdout || "No process output"
            ].join("\n")
          )
        );
      }
    });
  });
}