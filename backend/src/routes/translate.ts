import Router from "@koa/router";
import { Translate } from "@google-cloud/translate/build/src/v2/index.js";

const translate = new Translate();

export const translateRouter = new Router();

/**
 * POST /translate
 * Body: { texts: string[], targetLang: string, sourceLang?: string }
 * Returns: { translations: string[] }
 */
translateRouter.post("/translate", async (ctx) => {
  const { texts, targetLang, sourceLang } = ctx.request.body as {
    texts: string[];
    targetLang: string;
    sourceLang?: string;
  };

  if (!Array.isArray(texts) || !texts.length || !targetLang) {
    ctx.status = 400;
    ctx.body = { error: "texts (string[]) and targetLang are required" };
    return;
  }

  // Cap at 20 texts per request to avoid abuse
  if (texts.length > 20) {
    ctx.status = 400;
    ctx.body = { error: "Maximum 20 texts per request" };
    return;
  }

  const options: { from?: string; to: string } = { to: targetLang };
  if (sourceLang) options.from = sourceLang;

  const [translations] = await translate.translate(texts, options);
  const result = Array.isArray(translations) ? translations : [translations];

  ctx.body = { translations: result };
});

/**
 * POST /detect-language
 * Body: { text: string }
 * Returns: { language: string, confidence: number }
 */
translateRouter.post("/detect-language", async (ctx) => {
  const { text } = ctx.request.body as { text: string };

  if (!text) {
    ctx.status = 400;
    ctx.body = { error: "text is required" };
    return;
  }

  // Use first 500 chars for detection (enough for reliable results)
  const sample = text.slice(0, 500);
  const [detection] = await translate.detect(sample);
  const det = Array.isArray(detection) ? detection[0] : detection;

  ctx.body = { language: det.language, confidence: det.confidence };
});
