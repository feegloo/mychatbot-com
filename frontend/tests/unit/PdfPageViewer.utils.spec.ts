import { describe, it, expect } from 'vitest'
import {
  estimatePageHeight,
  detectSwipe,
  pointDistance,
  clampScale,
  computePinchScale,
  LruSet,
  isMobileUserAgent,
} from '../../src/components/PdfPageViewer.utils'

describe('estimatePageHeight', () => {
  it('computes height from aspect ratio and width minus padding, scaled', () => {
    // width 600, padding 24 → displayWidth 576; aspect 0.75 → height 768
    expect(estimatePageHeight(0.75, 600, 24, 1)).toBeCloseTo(768)
  })

  it('scales with user zoom', () => {
    expect(estimatePageHeight(1, 600, 24, 2)).toBeCloseTo((600 - 24) * 2)
  })

  it('returns 0 for non-positive aspect ratio', () => {
    expect(estimatePageHeight(0, 600, 24, 1)).toBe(0)
    expect(estimatePageHeight(-1, 600, 24, 1)).toBe(0)
  })
})

describe('detectSwipe', () => {
  it('returns null when below the horizontal threshold', () => {
    expect(detectSwipe(20, 0)).toBeNull()
  })

  it('detects a leftward swipe', () => {
    expect(detectSwipe(-80, 10)).toBe('left')
  })

  it('detects a rightward swipe', () => {
    expect(detectSwipe(80, -10)).toBe('right')
  })

  it('ignores mostly vertical gestures', () => {
    expect(detectSwipe(60, 200)).toBeNull()
  })

  it('ignores gestures beyond the angle threshold', () => {
    // dx=60, dy=60 → 45° > 30°
    expect(detectSwipe(60, 60)).toBeNull()
  })
})

describe('pointDistance', () => {
  it('computes Euclidean distance', () => {
    expect(pointDistance({ x: 0, y: 0 }, { x: 3, y: 4 })).toBe(5)
  })
})

describe('clampScale', () => {
  it('clamps below min', () => {
    expect(clampScale(0.1)).toBe(0.5)
  })
  it('clamps above max', () => {
    expect(clampScale(10)).toBe(3)
  })
  it('passes through values in range', () => {
    expect(clampScale(1.5)).toBe(1.5)
  })
  it('handles non-finite inputs', () => {
    expect(clampScale(NaN)).toBe(0.5)
  })
})

describe('computePinchScale', () => {
  it('doubles the scale when fingers move twice as far apart', () => {
    expect(computePinchScale(1, 100, 200)).toBe(2)
  })

  it('halves the scale when fingers converge', () => {
    expect(computePinchScale(2, 200, 100)).toBe(1)
  })

  it('clamps the result', () => {
    expect(computePinchScale(2, 100, 1000)).toBe(3)
    expect(computePinchScale(1, 100, 1)).toBe(0.5)
  })

  it('is safe when the initial distance is zero', () => {
    expect(computePinchScale(1, 0, 200)).toBe(1)
  })
})

describe('LruSet', () => {
  it('touch adds, and evicts the oldest entry at capacity', () => {
    const lru = new LruSet<number>(3)
    expect(lru.touch(1)).toBeUndefined()
    expect(lru.touch(2)).toBeUndefined()
    expect(lru.touch(3)).toBeUndefined()
    expect(lru.touch(4)).toBe(1)
    expect(lru.values()).toEqual([2, 3, 4])
  })

  it('touch re-orders an existing key without evicting', () => {
    const lru = new LruSet<number>(3)
    lru.touch(1)
    lru.touch(2)
    lru.touch(3)
    expect(lru.touch(1)).toBeUndefined()
    expect(lru.values()).toEqual([2, 3, 1])
  })

  it('delete removes a key', () => {
    const lru = new LruSet<number>(3)
    lru.touch(1)
    expect(lru.delete(1)).toBe(true)
    expect(lru.has(1)).toBe(false)
    expect(lru.delete(1)).toBe(false)
  })

  it('rejects invalid capacity', () => {
    expect(() => new LruSet<number>(0)).toThrow()
  })
})

describe('isMobileUserAgent', () => {
  it('matches iPhone', () => {
    expect(isMobileUserAgent('Mozilla/5.0 (iPhone; ...)')).toBe(true)
  })
  it('does not match desktop Chrome', () => {
    expect(isMobileUserAgent('Mozilla/5.0 (X11; Linux) Chrome/120')).toBe(false)
  })
})
