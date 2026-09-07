/**
 * @jarvis/sdk — Type Generation Script
 *
 * Fetches (or reads) the OpenAPI schema and generates TypeScript types.
 *
 *   npm run generate
 *   npm run generate -- --input ..\..\benchmarks\logs\openapi.json
 *   npm run generate:check
 */
const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');

const SCHEMA_URL = process.env.JARVIS_API_URL || 'http://127.0.0.1:8000';
// ``types.ts`` contains the SDK's compatibility aliases. Keep the raw
// OpenAPI output separate so regeneration cannot break those aliases.
const OUTPUT = process.env.JARVIS_OPENAPI_OUTPUT ||
  path.join(__dirname, '..', 'generated', 'openapi.ts');
const args = process.argv.slice(2);
const check = args.includes('--check');
const inputIndex = args.indexOf('--input');
const input = inputIndex >= 0 ? args[inputIndex + 1] : process.env.JARVIS_OPENAPI_FILE;

function fetchSchema(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https:') ? https : http;
    client.get(`${url.replace(/\/$/, '')}/openapi.json`, (res) => {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        res.resume();
        reject(new Error(`Backend returned HTTP ${res.statusCode}`));
        return;
      }
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => resolve(body));
    }).on('error', reject);
  });
}

async function main() {
  const schema = input
    ? fs.readFileSync(path.resolve(process.cwd(), input), 'utf8')
    : await fetchSchema(SCHEMA_URL);
  JSON.parse(schema);
  const schemaPath = path.join(__dirname, '..', 'generated', '.openapi.json');
  fs.writeFileSync(schemaPath, schema);
  const { execSync } = require('child_process');
  const generated = execSync(
    `npx openapi-typescript "${schemaPath}"`,
    { encoding: 'utf8', timeout: 120000 },
  );
  if (check) {
    const current = fs.readFileSync(OUTPUT, 'utf8');
    if (current !== generated) {
      throw new Error(`${OUTPUT} is out of date; run npm run generate`);
    }
  } else {
    fs.writeFileSync(OUTPUT, generated);
    console.log(`[generate-types] Wrote ${OUTPUT}`);
  }
  fs.rmSync(schemaPath, { force: true });
}

main().catch(console.error);
