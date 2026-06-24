/**
 * @jarvis/sdk — Type Generation Script
 *
 * Fetches the OpenAPI schema from the running backend and generates TypeScript types.
 * Run after backend changes: npm run generate
 */
const fs = require('fs');
const path = require('path');
const https = require('http');

const SCHEMA_URL = process.env.JARVIS_API_URL || 'http://127.0.0.1:8000';
const OUTPUT = path.join(__dirname, '..', 'generated', 'types.ts');

async function main() {
  console.log(`[generate-types] Fetching schema from ${SCHEMA_URL}/openapi.json ...`);

  // For now, use openapi-typescript CLI if available, otherwise copy the existing types
  const { execSync } = require('child_process');
  try {
    execSync(
      `npx --yes openapi-typescript "${SCHEMA_URL}/openapi.json" -o "${OUTPUT}"`,
      { stdio: 'inherit', timeout: 30000 },
    );
    console.log('[generate-types] Types generated from OpenAPI schema');
  } catch (e) {
    console.warn('[generate-types] openapi-typescript failed, keeping manual types');
    console.warn(e.message);
  }
}

main().catch(console.error);
