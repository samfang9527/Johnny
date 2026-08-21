import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'

const srcRoot = new URL('../src/', import.meta.url)
const allowedFile = 'styles.css'
const johnnyPalette = [
  '#5aa7b8',
  '#101820',
  '#0b1117',
  '#2b3138',
  '#f4f1e7',
  '#b7c1ba',
  '#f2b84b',
  '#b93e35',
  '#74a66a',
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
