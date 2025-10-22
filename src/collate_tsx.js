// collate-tsx.js
const fs = require('fs')
const path = require('path')

const rootDirs = ['components']
const outputPath = 'collated_components.txt'
const targetExtension = '.tsx'

const isTSX = (filename) => path.extname(filename) === targetExtension

function collectTSXFiles(dir) {
  let files = []

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name)

    if (entry.isDirectory()) {
      files = files.concat(collectTSXFiles(fullPath))
    } else if (isTSX(entry.name)) {
      files.push(fullPath)
    }
  }

  return files
}

function collateFiles(filePaths) {
  let output = ''

  for (const file of filePaths) {
    const content = fs.readFileSync(file, 'utf-8')
    output += `\n\n/* ===== ${file} ===== */\n\n${content}`
  }

  return output
}

// Run it
const allFiles = rootDirs.flatMap((dir) => collectTSXFiles(path.join(__dirname, dir)))
const combined = collateFiles(allFiles)

fs.writeFileSync(outputPath, combined)
console.log(`✅ Collated ${allFiles.length} .tsx files into: ${outputPath}`)
