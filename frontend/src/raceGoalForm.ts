export type RacePriority = 'primary' | 'secondary' | 'tune_up'

export const racePriorityOptions: Array<{ value: RacePriority; label: string }> = [
  { value: 'primary', label: '主要目標' },
  { value: 'secondary', label: '次要目標' },
  { value: 'tune_up', label: '暖身賽' },
]

export function kilometersToMeters(value: string): number | null {
  const normalized = value.trim()
  if (!/^\d+(?:\.\d{1,3})?$/.test(normalized)) {
    return null
  }
  const kilometers = Number(normalized)
  if (!Number.isFinite(kilometers) || kilometers <= 0 || kilometers > 500) {
    return null
  }
  return Math.round(kilometers * 1000)
}

export function formatRaceDistance(meters: number): string {
  if (!Number.isFinite(meters) || meters <= 0) {
    return 'N/A'
  }
  const kilometers = meters / 1000
  return `${Number(kilometers.toFixed(3)).toString()} km`
}

export function formatRacePriority(value: unknown): string {
  const option = racePriorityOptions.find((item) => item.value === value)
  return option?.label ?? ''
}

export function targetFinishSeconds(hours: string, minutes: string, seconds: string): number | undefined {
  const values = [hours, minutes, seconds].map((value) => (value.trim() === '' ? 0 : Number(value)))
  if (values.some((value) => !Number.isInteger(value) || value < 0)) {
    return undefined
  }
  const [parsedHours, parsedMinutes, parsedSeconds] = values
  const total = parsedHours * 3600 + parsedMinutes * 60 + parsedSeconds
  return total > 0 ? total : undefined
}
