import Koa from "koa";
import cors from "@koa/cors";
import bodyParser from "koa-bodyparser";
import path from "node:path";
import fs from "node:fs";
import serve from "koa-static";
import send from "koa-send";
import { uploadRouter } from "./routes/upload.js";
import { conversationsRouter } from "./routes/conversations.js";
import { askRouter } from "./routes/ask.js";
import { streamAnswerRouter } from "./routes/stream-answer.js";
import { healthRouter } from "./routes/health.js";
import { storageRouter } from "./routes/storage.js";
import { config } from "./config.js";

export function createApp() {
  const app = new Koa();

  app.use(cors());
  app.use(bodyParser());

  const apiRouter = uploadRouter
    .use(conversationsRouter.routes())
    .use(askRouter.routes())
    .use(streamAnswerRouter.routes())
    .use(healthRouter.routes())
    .use(storageRouter.routes());

  app.use(async (ctx, next) => {
    if (ctx.path.startsWith("/api")) {
      return next();
    }
    return next();
  });

  app.use(async (ctx, next) => {
    if (ctx.path.startsWith("/api")) {
      ctx.path = ctx.path.replace(/^\/api/, "") || "/";
      return apiRouter.routes()(ctx, next);
    }
    return next();
  });

  if (config.frontendDistPath && fs.existsSync(config.frontendDistPath)) {
    app.use(serve(config.frontendDistPath));

    app.use(async (ctx) => {
      if (ctx.path.startsWith("/api")) return;
      await send(ctx, "index.html", { root: path.resolve(config.frontendDistPath) });
    });
  }

  return app;
}
