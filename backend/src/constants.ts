export const CONVERSATION_TOKEN_HEADER = 'x-conversation-token'

export const SHORT_ID_RE = /^[0-9A-Za-z]{16}$/

export const IMAGE_EXTENSIONS = new Set([
  '.jpg',
  '.jpeg',
  '.png',
  '.gif',
  '.webp',
  '.bmp',
  '.tiff',
  '.tif',
])

export const VIDEO_EXTENSIONS = new Set(['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm'])

export const MAX_FILE_SIZE = 100 * 1024 * 1024 // 100 MB
