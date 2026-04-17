import Router from "@koa/router";
import { config } from "../config.js";

export const synthesizeRouter = new Router();

/**
 * POST /synthesize
 * Body: { text: string; language?: string }
 * Returns: audio/mpeg binary (MP3)
 *
 * Uses OpenAI TTS API (tts-1 model, "nova" voice — soft female).
 * Language is auto-detected from the text by the API if not provided.
 */
synthesizeRouter.post("/synthesize", async (ctx) => {
  const { text, language } = ctx.request.body as {
    text: string;
    language?: string;
  };

  if (!text || typeof text !== "string") {
    ctx.status = 400;
    ctx.body = { error: "text (string) is required" };
    return;
  }

  // Cap text length to prevent abuse
  if (text.length > 2000) {
    ctx.status = 400;
    ctx.body = { error: "Maximum 2000 characters per request" };
    return;
  }

  const apiKey = config.openAiApiKey;
  if (!apiKey) {
    ctx.status = 503;
    ctx.body = { error: "TTS service not configured" };
    return;
  }

  try {
    // If a language hint is provided, prepend an invisible instruction
    // to help the model pronounce in the right language
    let input = text;
    if (language) {
      // The TTS model respects language from input text; no special prefix needed
      // for most languages. Just pass the text as-is.
      input = text;
    }

    const response = await fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "tts-1",
        input,
        voice: "nova",
        response_format: "mp3",
        speed: 1.0,
      }),
    });

    if (!response.ok) {
      const errBody = await response.text();
      console.error("OpenAI TTS error:", response.status, errBody);
      ctx.status = 502;
      ctx.body = { error: "TTS service error" };
      return;
    }

    const audioBuffer = Buffer.from(await response.arrayBuffer());
    ctx.set("Content-Type", "audio/mpeg");
    ctx.set("Content-Length", String(audioBuffer.length));
    ctx.set("Cache-Control", "no-store");
    ctx.body = audioBuffer;
  } catch (err: any) {
    console.error("TTS synthesis error:", err.message);
    ctx.status = 502;
    ctx.body = { error: "TTS service unavailable" };
  }
});
