/**
 * Clean build artifacts.
 */
const fs = require('fs');
const path = require('path');

const dirs = [
  path.join(__dirname, '..', 'out'),
  path.join(__dirname, '..', '.next'),
];

for (const dir of dirs) {
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
    console.log(`Cleaned: ${dir}`);
  }
}
