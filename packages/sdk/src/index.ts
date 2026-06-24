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
