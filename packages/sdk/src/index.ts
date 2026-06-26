/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Barrel Export
 *
 * Import from this package to get typed access to all JARVIS backend APIs.
 *
 * Usage:
 *   import { activity, agents, ActivityStream } from '@jarvis/sdk';
 *
 *   const activities = await activity.list();
 *   const stream = new ActivityStream();
 *   stream.onUpdated((e) => console.log(e.status));
 * ─────────────────────────────────────────────────────────────────────────── */
export * from '../generated/types';
export { request, api, ApiError, getTokenForWs } from './client';
export { ActivityStream } from './websocket';
export { activity } from './activity';
export { agents } from './agents';
export { artifacts } from './artifacts';
export { workflows } from './workflows';
export { scheduler } from './scheduler';
export { knowledge } from './knowledge';
export { research } from './research';
export { plans } from './plans';
export { analytics } from './analytics';
export { improvements } from './improvements';
export { negotiations } from './negotiations';
export { opportunities } from './opportunities';
export { autonomous } from './autonomous';
export { evidence } from './evidence';

// ── Phase 1 modules ───────────────────────────────────────────────────────
export { auth } from './auth';
export { automation } from './automation';
export { build } from './build';
export { channels } from './channels';
export { chat } from './chat';
export { code } from './code';
export { commitments } from './commitments';
export { dashboard } from './dashboard';
export { diagnostics } from './diagnostics';
export { email } from './email';
export { features } from './features';
export { files } from './files';
export { horizon } from './horizon';
export { infrastructure } from './infrastructure';
export { integrations } from './integrations';
export { mcp } from './mcp';
export { media } from './media';
export { memory } from './memory';
export { models } from './models';
export { notes } from './notes';
export { plugins } from './plugins';
export { projects } from './projects';
export { quality } from './quality';
export { reminders } from './reminders';
export { scene } from './scene';
export { settings } from './settings';
export { skills } from './skills';
export { system } from './system';
export { vision } from './vision';
export { voice } from './voice';
