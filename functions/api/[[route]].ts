/**
 * Cloudflare Pages Functions — catch-all for /api/*
 * 기존 Hono worker(server/src/worker.ts)를 Pages Function으로 래핑
 */
import app from '../../server/src/worker';
import type { Env } from '../../server/src/worker';

export const onRequest: PagesFunction<Env> = (context) => {
  return app.fetch(context.request, context.env as Env, context.executionCtx);
};
