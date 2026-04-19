import type { Context } from 'koa'
import { CONVERSATION_TOKEN_HEADER } from '../constants.js'

export function getConversationToken(ctx: Context): string {
  return String(ctx.headers[CONVERSATION_TOKEN_HEADER] || '')
}
