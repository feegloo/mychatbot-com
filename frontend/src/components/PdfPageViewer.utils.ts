/**
 * Pure helpers for {@link PdfPageViewer.vue}. Kept separate so they can be
 * reasoned about and unit-tested without pulling in pdf.js or a DOM.
 */

export const MOBILE_UA_RE = /iPhone|iPad|iPod|Android/i

export function isMobileUserAgent(ua: string = navigator.userAgent): boolean {
  return MOBILE_UA_RE.test(ua)
}

/**
 * Estimate a page's rendered height from an aspect ratio and container width.
 * Used to pre-size page placeholders before a page has actually rendered so
 * the scrollable document has the correct total length from the start.
 */
export function estimatePageHeight(
  aspectRatio: number,
  containerWidth: number,
  horizontalPadding: number,
  userScale: number,
): number {
  const displayWidth = Math.max(0, containerWidth - horizontalPadding) * userScale
  if (aspectRatio <= 0) return 0
  return displayWidth / aspectRatio
}

export interface Point {
  x: number
  y: number
}

/**
 * Classify a horizontal gesture as a left/right swipe, or null if it's too
 * short, too diagonal, or primarily vertical (which should remain a scroll).
 */
export function detectSwipe(
  dx: number,
  dy: number,
  minDistance = 50,
  maxAngleDeg = 30,
): 'left' | 'right' | null {
  const absDx = Math.abs(dx)
  if (absDx < minDistance) return null
  const angleDeg = (Math.atan2(Math.abs(dy), absDx) * 180) / Math.PI
  if (angleDeg > maxAngleDeg) return null
  return dx < 0 ? 'left' : 'right'
}

/** Euclidean distance between two points. */
export function pointDistance(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y)
}

/** Clamp a user zoom value to the viewer's supported range. */
export function clampScale(scale: number, min = 0.5, max = 3): number {
  if (!Number.isFinite(scale)) return min
  return Math.min(max, Math.max(min, scale))
}

/**
 * Compute a new scale from a two-finger pinch given the initial finger
 * distance and the current distance. The result is clamped to [min, max].
 */
export function computePinchScale(
  initialScale: number,
  initialDistance: number,
  currentDistance: number,
  min = 0.5,
  max = 3,
): number {
  if (initialDistance <= 0) return clampScale(initialScale, min, max)
  const ratio = currentDistance / initialDistance
  return clampScale(initialScale * ratio, min, max)
}

/**
 * Minimal LRU set: `touch(key)` moves the key to the front and returns any
 * evicted key when capacity is exceeded. Used to cap the number of
 * simultaneously-rendered PDF pages so huge documents don't OOM the tab.
 */
export class LruSet<K> {
  private readonly order: K[] = []

  constructor(private readonly capacity: number) {
    if (capacity < 1) throw new Error('LruSet capacity must be >= 1')
  }

  touch(key: K): K | undefined {
    const idx = this.order.indexOf(key)
    if (idx !== -1) this.order.splice(idx, 1)
    this.order.push(key)
    if (this.order.length > this.capacity) return this.order.shift()
    return undefined
  }

  delete(key: K): boolean {
    const idx = this.order.indexOf(key)
    if (idx === -1) return false
    this.order.splice(idx, 1)
    return true
  }

  has(key: K): boolean {
    return this.order.includes(key)
  }

  size(): number {
    return this.order.length
  }

  values(): K[] {
    return [...this.order]
  }

  clear(): void {
    this.order.length = 0
  }
}
