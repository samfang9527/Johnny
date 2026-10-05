import { describe, expect, it } from 'vitest'
import { kilometersToMeters, optionalCourseMeters, optionalCutoffSeconds } from './raceGoalForm'

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

describe('optional race course inputs', () => {
  it('keeps blank values unknown and converts entered values', () => {
    expect(optionalCourseMeters('')).toBeUndefined()
    expect(optionalCourseMeters('1250')).toBe(1250)
    expect(optionalCutoffSeconds('')).toBeUndefined()
    expect(optionalCutoffSeconds('8')).toBe(28800)
  })

  it('rejects negative ascent and nonpositive cutoffs', () => {
    expect(optionalCourseMeters('-1')).toBeNull()
    expect(optionalCutoffSeconds('0')).toBeNull()
    expect(optionalCutoffSeconds('-2')).toBeNull()
  })
})
