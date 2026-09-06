// E4-16 acceptance criterion 1: a planted red component test, pushed once so the
// new CI vitest step is watched failing, then removed. Never merged.
import { describe, expect, it } from 'vitest'

describe('the planted red proof', () => {
  it('fails on purpose so the vitest CI step is seen refusing', () => {
    expect(true).toBe(false)
  })
})
