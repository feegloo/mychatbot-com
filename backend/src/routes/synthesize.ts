import Router from "@koa/router";
import { config } from "../config.js";
import { Translate } from "@google-cloud/translate/build/src/v2/index.js";

const translateClient = new Translate();

export const synthesizeRouter = new Router();

/**
 * POST /synthesize
 * Body: { text: string; language?: string; instructions?: string }
 * Returns: audio/mpeg binary (MP3)
 *
 * Uses OpenAI TTS API (gpt-4o-mini-tts model, "nova" voice — soft female).
 * Supports optional `instructions` for tone/style control.
 * Language is auto-detected from the text by the API if not provided.
 */
synthesizeRouter.post("/synthesize", async (ctx) => {
  const { text, language, instructions } = ctx.request.body as {
    text: string;
    language?: string;
    instructions?: string;
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

    const ttsPayload: Record<string, unknown> = {
      model: "gpt-4o-mini-tts",
      input,
      voice: "shimmer",
      response_format: "mp3",
    };
    if (instructions) ttsPayload.instructions = instructions;

    const response = await fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(ttsPayload),
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

// ── Helper functions for word-level captions ──

async function getWordTimestamps(
  audioBuffer: Buffer,
  apiKey: string,
): Promise<Array<{ word: string; start: number; end: number }>> {
  try {
    const blob = new Blob([new Uint8Array(audioBuffer)], { type: "audio/mpeg" });
    const formData = new FormData();
    formData.append("file", blob, "speech.mp3");
    formData.append("model", "whisper-1");
    formData.append("response_format", "verbose_json");
    formData.append("timestamp_granularities[]", "word");

    const response = await fetch(
      "https://api.openai.com/v1/audio/transcriptions",
      {
        method: "POST",
        headers: { Authorization: `Bearer ${apiKey}` },
        body: formData,
      },
    );

    if (!response.ok) {
      console.error("Whisper error:", response.status, await response.text());
      return [];
    }

    const data = (await response.json()) as {
      words?: Array<{ word: string; start: number; end: number }>;
    };
    return data.words || [];
  } catch (err: any) {
    console.error("Whisper transcription error:", err.message);
    return [];
  }
}

async function translateForCaptions(
  text: string,
  targetLang: string,
  sourceLang?: string,
): Promise<string | undefined> {
  try {
    const options: { from?: string; to: string } = { to: targetLang };
    if (sourceLang) options.from = sourceLang;
    const [translation] = await translateClient.translate(text, options);
    return Array.isArray(translation) ? translation[0] : translation;
  } catch (err: any) {
    console.error("Translation for captions error:", err.message);
    return undefined;
  }
}

/**
 * POST /synthesize-with-captions
 * Body: { text: string; language?: string; translateTo?: string }
 * Returns: { audio: base64, captions: [{word, start, end}], translatedText?: string }
 *
 * Generates TTS audio, extracts word-level timestamps via Whisper,
 * and optionally translates text for ghost-word display.
 */
synthesizeRouter.post("/synthesize-with-captions", async (ctx) => {
  const { text, language, translateTo, instructions } = ctx.request.body as {
    text: string;
    language?: string;
    translateTo?: string;
    instructions?: string;
  };

  if (!text || typeof text !== "string") {
    ctx.status = 400;
    ctx.body = { error: "text (string) is required" };
    return;
  }

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
    // 1. Generate TTS audio
    const ttsPayload: Record<string, unknown> = {
      model: "gpt-4o-mini-tts",
      input: text,
      voice: "shimmer",
      response_format: "mp3",
    };
    if (instructions) ttsPayload.instructions = instructions;

    const ttsResponse = await fetch("https://api.openai.com/v1/audio/speech", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(ttsPayload),
    });

    if (!ttsResponse.ok) {
      const errBody = await ttsResponse.text();
      console.error("OpenAI TTS error:", ttsResponse.status, errBody);
      ctx.status = 502;
      ctx.body = { error: "TTS service error" };
      return;
    }

    const audioBuffer = Buffer.from(await ttsResponse.arrayBuffer());

    // Count words in input to decide whether Whisper is needed
    const wordCount = text.trim().split(/\s+/).length;

    // 2. Run Whisper (skip for single word) + Translation in parallel
    const whisperPromise =
      wordCount > 1
        ? getWordTimestamps(audioBuffer, apiKey).catch((err) => {
            console.error("Whisper failed, returning null captions:", err);
            return null;
          })
        : Promise.resolve(null);

    const translatePromise =
      translateTo && translateTo !== language
        ? translateForCaptions(text, translateTo, language)
        : Promise.resolve(undefined);

    const [captions, translatedText] = await Promise.all([
      whisperPromise,
      translatePromise,
    ]);

    // Whisper returned empty array → treat as null
    const finalCaptions =
      Array.isArray(captions) && captions.length > 0 ? captions : null;

    // 3. Return JSON with base64 audio + captions (null when unavailable)
    ctx.body = {
      audio: audioBuffer.toString("base64"),
      captions: finalCaptions,
      ...(translatedText ? { translatedText } : {}),
    };
  } catch (err: any) {
    console.error("TTS with captions error:", err.message);
    ctx.status = 502;
    ctx.body = { error: "TTS service unavailable" };
  }
});
