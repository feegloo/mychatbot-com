import Router from "@koa/router";

export const healthRouter = new Router();

healthRouter.get("/health", async (ctx) => {
  ctx.body = { ok: true };
});
