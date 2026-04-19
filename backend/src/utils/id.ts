import crypto from 'node:crypto'

const BASE62_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

/** Generate a 16-character base62 random ID (~95.2 bits of entropy). */
export function generateShortId(length = 16): string {
  const bytes = crypto.randomBytes(length)
  let result = ''
  for (let i = 0; i < length; i++) {
    result += BASE62_CHARS[bytes[i] % 62]
  }
  return result
}
