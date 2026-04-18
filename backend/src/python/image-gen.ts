import { config } from "../config.js";

export async function generateImage(options: {
  question: string;
  storageDir: string;
  context?: string;
  welcomeMessages?: string[];
  size?: string;
}) {
  const response = await fetch(`${config.pythonServerUrl}/generate-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: options.question,
      storage_dir: options.storageDir,
      context: options.context || "",
      welcome_messages: options.welcomeMessages || [],
      size: options.size || "1024x1024",
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Python server error (${response.status}): ${text}`);
  }

  return (await response.json()) as {
    file_name: string;
    revised_prompt: string;
    image_prompt: string;
  };
}
