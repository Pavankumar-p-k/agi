/**
 * Production build verification script.
 * Checks that the static export is complete and well-formed.
 */
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..', 'out');
const REQUIRED_FILES = [
  'index.html',
  'manifest.json',
  '_next/static/chunks',
];

const REQUIRED_ROUTES = [
  'index.html',
  'chat/index.html',
  'cli/index.html',
  'monitor/index.html',
  'logs/index.html',
  'backend/index.html',
  'settings/index.html',
  'settings/themes/index.html',
  'settings/fonts/index.html',
  'auth/login/index.html',
];

let errors = 0;

for (const file of REQUIRED_FILES) {
  const p = path.join(OUT, file);
  if (!fs.existsSync(p)) {
    console.error(`MISSING: ${file}`);
    errors++;
  }
}

for (const route of REQUIRED_ROUTES) {
  const p = path.join(OUT, route);
  if (!fs.existsSync(p)) {
    console.error(`MISSING ROUTE: ${route}`);
    errors++;
  }
}

const indexPath = path.join(OUT, 'index.html');
if (fs.existsSync(indexPath)) {
  const content = fs.readFileSync(indexPath, 'utf-8');
  if (!content.includes('JARVIS')) {
    console.error('ERROR: index.html does not contain "JARVIS"');
    errors++;
  }
  if (!content.includes('_next')) {
    console.error('ERROR: index.html does not reference _next chunks');
    errors++;
  }
}

const totalSize = getDirSize(OUT);
const sizeMB = (totalSize / 1024 / 1024).toFixed(1);
console.log(`\nBuild output: ${OUT}`);
console.log(`Total size: ${sizeMB} MB`);
console.log(`Routes: ${REQUIRED_ROUTES.length} core pages`);
console.log(`Errors: ${errors}`);

if (errors > 0) {
  console.error('\nBUILD VERIFICATION FAILED');
  process.exit(1);
} else {
  console.log('\nBUILD VERIFICATION PASSED');
}

function getDirSize(dir) {
  let size = 0;
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        size += getDirSize(full);
      } else if (entry.isFile()) {
        size += fs.statSync(full).size;
      }
    }
  } catch { /* skip */ }
  return size;
}
