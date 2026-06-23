# WEB UI Audit

Generated: 2026-06-14

## Architecture

The JARVIS web frontend is a **Next.js 14 App Router** SPA with `output: 'export'` (static HTML), served by the FastAPI backend as static files.

```
web/ → Next.js 14 static export → FastAPI catch-all route
static/ → Legacy static HTML SPA (fallback)
```

### Routes (10 pages)

| Route | Component | Auth Required |
|-------|-----------|--------------|
| `/` | Dashboard | No |
| `/chat` | Chat Interface | No |
| `/cli` | CLI Showcase | No |
| `/monitor` | System Monitor | No |
| `/logs` | Log Viewer (WebSocket) | No |
| `/backend` | Backend Control | No |
| `/settings` | Settings Core | No |
| `/settings/themes` | Theme Studio | No |
| `/settings/fonts` | Font Engine | No |
| `/auth/login` | Login Page | No |

### Backend Dependencies
- FastAPI + Uvicorn
- 7 WebSocket endpoints (/ws/chat_stream, /ws/logs, etc.)
- 200+ REST endpoints across 38 router files
- Session auth via `core/auth.py` (AuthManager)

---

## Findings

### CRITICAL

#### C1. Login endpoint missing on backend

**File:** `web/src/app/auth/login/page.tsx:25` calls `POST /api/auth/login`
**File:** `core/routes/auth.py` — no `POST /auth/login` or `POST /api/auth/login` endpoint

The login form sends username/password to a route that **does not exist** on the backend. Backend auth routes only expose OAuth login (`GET /auth/login/{provider}`). The frontend password login will always fail with a 404.

**Fix needed:** Add `POST /auth/login` endpoint that delegates to `AuthManager.authenticate()`.

#### C2. Auth token never sent with API requests

**File:** `web/src/lib/api.ts` — `request()` function doesn't read `localStorage('j-token')`

The login page stores a JWT in `localStorage('j-token')` (line 32), but the API client never attaches it. All authenticated API calls will receive 401 responses.

**Fix needed:** Add `Authorization: Bearer <token>` header injection in `api.ts`.

#### C3. Auth token never sent with WebSocket connections

**File:** `web/src/lib/ws.ts` — constructor doesn't include auth token

WebSocket connections to `/ws/chat_stream`, `/ws/logs`, etc. don't include any authentication token. The backend may reject these connections if auth is enabled.

**Fix needed:** Pass token as query parameter or during WebSocket handshake.

#### C4. No frontend auth guard

**File:** `web/src/app/ClientShell.tsx` — no auth check before rendering pages

All routes render without checking if the user is authenticated. If the backend requires auth, unauthenticated users get 401 errors rendered as blank states.

**Fix needed:** Add AuthContext provider and auth guard wrapper.

### HIGH

#### H1. Duplicate POST /api/chat route

**Files:** `core/routes/operations.py:55` and `core/routes/chat.py:30` both register `POST /api/chat`

The operations.py route is the "simple" version (no auth, minimal logic), while chat.py has a more complete version. The second registration silently overrides the first.

**Fix needed:** Remove the duplicate from operations.py.

#### H2. Manifest.json and PWA

**File:** `web/src/app/layout.tsx:8` references `/manifest.json`
**Backend:** `core/main.py` serves `static/manifest.json`

The Next.js app references a manifest, but the static export doesn't generate one at the root. The backend serves the legacy manifest from `static/manifest.json`, which references icons in `/assets/` (legacy). The Next.js `public/manifest.json` with proper PWA icons is never used.

**Fix needed:** Copy the proper manifest to the static export output.

#### H3. No production build pipeline

No Dockerfile, no CI script, no post-build validation for the web UI. The `package.json` has no `build:production` or `deploy` script. No mechanism to verify production output.

**Fix needed:** Create production build pipeline with Docker, health checks, and validation.

#### H4. No frontend health check component

The backend has `/health` endpoint, but the frontend has no dedicated health check page or component. Health status is only shown inline on the dashboard and settings page.

**Fix needed:** Add a reusable health check component.

### MEDIUM

#### M1. Theme CSS redundancy

**Files:** `web/src/styles/globals.css:12-38` defines CSS vars in `:root`
**Files:** `web/src/styles/themes/sky.css`, `phantom.css`, etc. redefine same vars under `.theme-sky`, `.theme-phantom`, etc.

The `:root` block duplicates the `theme-sky` values. When another theme is active, the `:root` defaults may leak.

**Fix needed:** Remove `:root` defaults, only define under theme classes.

#### M2. No per-page error boundaries

Only `ClientShell.tsx` wraps content in `ErrorBoundary`. Individual pages have no fallback UI for errors.

**Fix needed:** Add error boundaries or error.tsx files per route group.

#### M3. Backend catch-all route may not handle trailing slashes

**File:** `core/main.py` catch-all route (`/{path:path}`)
**Config:** `next.config.js` has `trailingSlash: true`

The static export generates files with trailing slashes (e.g., `/chat/index.html`). The backend catch-all must serve these correctly. Currently the fallback chain is: try `web/out/{path}/index.html` → fallback to `static/index.html`.

**Fix needed:** Verify and harden the catch-all static file serving.

#### M4. Settings stored only in localStorage

**File:** `web/src/app/settings/page.tsx` — prefs saved to `localStorage('jarvis:settings')`

No server-side sync. Settings are lost if localStorage is cleared or user switches browsers.

**Fix needed:** Add option to sync settings to backend API.

### LOW

#### L1. No image optimization

**File:** `web/next.config.js` — `images: { unoptimized: true }`

Required for static export but means all images are served at full resolution.

#### L2. No CSP Content Security Policy

The backend has `SecurityHeadersMiddleware` with CSP, but inline styles (via `style={}` in JSX) would be blocked by strict CSP. The current CSP likely allows `unsafe-inline`.

#### L3. No offline support for Next.js app

The legacy `static/sw.js` has cache-first strategy, but the Next.js app has no service worker for offline access.

#### L4. No loading states for auth

Login page has loading state, but auth check on page load doesn't show a loading spinner.

---

## Acceptance Criteria Assessment

| Criterion | Status |
|-----------|--------|
| `npm build` succeeds | ✅ Currently passes |
| Production bundle generated | ✅ Static export to `web/out/` |
| Authentication works | ❌ Login endpoint missing, token never sent |
| Real-time updates work | ⚠️ WebSocket works but no auth |
| No console errors | ⚠️ Runtime errors expected from 401 responses |
| Lighthouse score >90 | ⚠️ Not tested — inline styles penalize CSP |

---

## Remediation Plan

### Phase 1 — Fix Auth (C1, C2, C3, C4)
1. Add `POST /auth/login` endpoint to `core/routes/auth.py`
2. Add auth token injection to `lib/api.ts`
3. Add auth token to `lib/ws.ts` WebSocket connections
4. Create AuthContext provider with auth guard

### Phase 2 — Fix Infrastructure (H1, H2, H3, H4)
1. Remove duplicate `POST /api/chat` from operations.py
2. Copy PWA manifest to static export
3. Create production build pipeline (Dockerfile, scripts)
4. Add frontend health check component

### Phase 3 — Polish (M1-M4, L1-L4)
1. Clean up theme CSS
2. Add error boundaries
3. Harden catch-all route
4. Add settings sync option
