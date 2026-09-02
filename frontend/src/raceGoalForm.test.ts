import { describe, expect, it } from 'vitest'
import { kilometersToMeters } from './raceGoalForm'

describe('race goal form helpers', () => {
  it('converts kilometers to integer meters with marathon precision', () => {
    expect(kilometersToMeters('42.195')).toBe(42195)
    expect(kilometersToMeters('10')).toBe(10000)
  })

  it('rejects non-positive, over-precise, and impractical kilometer values', () => {
    expect(kilometersToMeters('0')).toBeNull()
    expect(kilometersToMeters('10.1234')).toBeNull()
    expect(kilometersToMeters('501')).toBeNull()
  })
})
