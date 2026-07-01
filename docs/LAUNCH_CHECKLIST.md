# JARVIS v3 Launch Checklist

## Pre-Launch Validation

### Clean Install
- [ ] `pip install jarvis-ai` succeeds on a clean machine
- [ ] No missing dependencies
- [ ] Windows install succeeds (PowerShell, no Unix assumptions)
- [ ] Linux install succeeds (Python 3.10+)
- [ ] macOS install succeeds (if supported)

### First-Run Experience
- [ ] `jarvis` auto-launches setup on first run
- [ ] Welcome wizard renders (no sidebar, no navbar)
- [ ] System Check detects hardware correctly (RAM, GPU, OS)
- [ ] Playwright installs in one click
- [ ] Model download shows real-time progress
- [ ] Recommended model matches hardware tier
- [ ] Demo runs and completes
- [ ] Setup completion redirects to Home
- [ ] Second run skips setup (idempotency)

### Core UX
- [ ] Home page loads with system readiness indicators
- [ ] Command input accepts queries and routes to Chat
- [ ] Quick action buttons execute
- [ ] Chat connects via WebSocket
- [ ] Chat messages stream in real time
- [ ] Pipeline animation shows during message processing
- [ ] Tasks page loads with running/pending/completed states
- [ ] History page groups items by date
- [ ] System page shows CPU, memory, disk gauges
- [ ] Provider Manager displays all providers
- [ ] Capability Graph renders all 9 internal providers

### Explain Page
- [ ] `/explain/[id]` loads for any activity
- [ ] Pipeline visualization shows active stages
- [ ] Summary metrics display correctly
- [ ] Timeline renders chronological events
- [ ] Decision traces show candidate scores
- [ ] Execution tree renders with expand/collapse
- [ ] Knowledge items display when available

### Navigation
- [ ] Sidebar items navigate to correct pages
- [ ] Dev Mode toggle persists across page loads
- [ ] Dev Mode reveals infrastructure pages
- [ ] Command palette opens and searches
- [ ] Keyboard shortcuts work (Ctrl+K, etc.)
- [ ] Skip link visible on first Tab press
- [ ] All 32 routes accessible via direct URL

### Integrations (Gate 2)
- [ ] Ollama model download with progress bar
- [ ] Playwright one-click install from Home page
- [ ] GitHub PAT entry and validation
- [ ] GitHub OAuth flow (if configured)
- [ ] API keys page shows all credential settings
- [ ] API keys validate on save
- [ ] API keys show validation status inline

### Settings
- [ ] Model Settings: download, select primary, toggle mode
- [ ] Integration Settings: connect/disconnect GitHub
- [ ] API Keys: view, update, validate
- [ ] Theme picker works across all pages
- [ ] Font settings apply globally

### Error Handling
- [ ] Every error state has a Retry button
- [ ] Error messages are human-friendly (not technical)
- [ ] Network failures show actionable messages
- [ ] Provider failures show suggestions (e.g., "Install Playwright")
- [ ] 404 pages render correctly

### Accessibility
- [ ] Skip link works
- [ ] All interactive elements have focus-visible outlines
- [ ] ARIA labels on all interactive elements
- [ ] Heading hierarchy is logical (h1 → h2 → h3)
- [ ] Color contrast meets WCAG AA standards
- [ ] Screen reader can navigate all pages
- [ ] Toast notifications have `aria-live`
- [ ] Command palette has `role="dialog"` and `role="listbox"`

## Build & Packaging (Gate 3)

### Python Package
- [ ] `pyproject.toml` configured for PyPI
- [ ] Dependencies pinned and tested
- [ ] Package name `jarvis-ai` available on PyPI
- [ ] `pip install jarvis-ai` pulls all dependencies
- [ ] CLI entry point registered
- [ ] Version bump (v3.0.0-rc2 → v3.0.0)

### Web Frontend
- [ ] `npm run build` succeeds (zero errors)
- [ ] `output: export` generates static files
- [ ] API proxy configured for production
- [ ] All environment variables documented

### Docker (if supported)
- [ ] Dockerfile builds cleanly
- [ ] docker-compose.yml works
- [ ] Container starts without errors

## Launch Assets (Gate 4)

### Website
- [ ] Product website live
- [ ] Tagline: "Local-first AI workspace"
- [ ] Feature overview matches v3 capabilities
- [ ] System requirements listed
- [ ] Installation instructions
- [ ] Link to documentation

### Screenshots
- [ ] Welcome wizard
- [ ] Home page
- [ ] Chat interface
- [ ] Explain page pipeline
- [ ] Provider Manager
- [ ] System health page
- [ ] Tasks page
- [ ] Settings pages

### Demo Content
- [ ] 30–60 second demo GIF
- [ ] 2–3 minute launch video (screen recording)
- [ ] Sample commands shown
- [ ] Pipeline visualization shown
- [ ] Setup → Demo → Home flow shown

### Documentation (`docs/`)
- [ ] `VISION.md` — product vision
- [ ] `PRODUCT.md` — what JARVIS does
- [ ] `ARCHITECTURE.md` — how it works
- [ ] `UX_PRINCIPLES.md` — design philosophy
- [ ] `ROADMAP.md` — v3.x and v4 plans
- [ ] `CONTRIBUTING.md` — how to contribute
- [ ] Quickstart guide (`README.md`)
- [ ] FAQ
- [ ] Troubleshooting guide

### Release Notes
- [ ] Changelog written
- [ ] Breaking changes documented
- [ ] Upgrade instructions from v2.x
- [ ] Known issues listed

## Final Validation

### End-to-End
- [ ] Clean install → setup → demo → home
- [ ] Chat conversation → save → reload
- [ ] Task creation → completion
- [ ] Model download → use → switch
- [ ] Provider failure → retry → success

### Regression
- [ ] All existing benchmarks pass
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] 2-hour soak test (0% memory leak, 0 exceptions)
- [ ] No console errors on any page

### Security
- [ ] API keys stored in vault (not localStorage)
- [ ] No secrets in client-side code
- [ ] CORS configured correctly
- [ ] Authentication required for all private routes

## Sign-off

| Gate | Reviewer | Date | Status |
|------|----------|------|--------|
| Gate 1 — UX | | | |
| Gate 2 — Integration Polish | | | |
| Gate 3 — Packaging | | | |
| Gate 4 — Launch Assets | | | |
| GA Release | | | |
