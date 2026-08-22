import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'

const srcRoot = new URL('../src/', import.meta.url)
const allowedFile = 'styles.css'
const johnnyPalette = [
  '#83b7a5',
  '#171b1a',
  '#111514',
  '#2f3430',
  '#f6efe4',
  '#c8c0b3',
  '#e8b86d',
  '#b85a50',
  '#8fb879',
  '#ffffff',
]

async function collectFiles(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  const files = await Promise.all(
    entries.map(async (entry) => {
      const fullPath = join(dir, entry.name)
      if (entry.isDirectory()) {
        return collectFiles(fullPath)
      }
      return fullPath
    }),
  )
  return files.flat()
}

const files = await collectFiles(srcRoot.pathname)
const offenders = []

for (const file of files) {
  const rel = relative(srcRoot.pathname, file)
  if (rel === allowedFile) {
    continue
  }
  const content = (await readFile(file, 'utf8')).toLowerCase()
  const matches = johnnyPalette.filter((token) => content.includes(token))
  if (matches.length > 0) {
    offenders.push(`${rel}: ${matches.join(', ')}`)
  }
}

if (offenders.length > 0) {
  console.error('Johnny palette values must stay centralized in src/styles.css.')
  for (const offender of offenders) {
    console.error(`- ${offender}`)
  }
  process.exit(1)
}

console.log('Johnny palette values are centralized in src/styles.css.')
