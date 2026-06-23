# Web UI Deployment Guide

## Architecture

The JARVIS web UI is a Next.js 14 static export served by the FastAPI backend.

```
Browser → FastAPI (port 8000) → WebSocket ↔ AI Engine
                    ↓
            static/    web/out/
            (legacy)   (Next.js export)
```

Two serving modes:
1. **Standalone** — Nginx serves the static export (Docker)
2. **Bundled** — FastAPI serves the static export (default)

## Quick Start

```bash
# Development
cd web && npm run dev

# Production build
cd web && npm run build

# Verify build
cd web && npm run verify
```

## Docker Deployment

```bash
# Build the web UI container
docker build -t jarvis-web web/

# Run with nginx
docker run -d -p 8080:80 jarvis-web
```

## Bundled with Backend

The FastAPI backend auto-detects the Next.js export:

1. Build the web UI: `cd web && npm run build`
2. Start JARVIS: `python jarvis.py web --host 0.0.0.0 --port 8000`

The backend serves:
- `web/out/` → Next.js static export (primary)
- `static/` → Legacy HTML (fallback)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Backend API URL |
| `NEXT_PUBLIC_WS_URL` | `ws://127.0.0.1:8000` | WebSocket URL |

For production behind a reverse proxy, set these to the public URL:
```
NEXT_PUBLIC_API_URL=https://jarvis.example.com
NEXT_PUBLIC_WS_URL=wss://jarvis.example.com
```

## Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl;
    server_name jarvis.example.com;

    # Proxy API requests to FastAPI
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Proxy WebSocket connections
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # Serve static web UI
    location / {
        root /path/to/jarvis/web/out;
        try_files $uri $uri/ $uri.html /index.html;
        expires 1h;
        add_header Cache-Control "public, must-revalidate";
    }
}
```

## Health Check

```bash
# Backend health
curl http://localhost:8000/api/health

# Web UI availability
curl -o /dev/null -w "%{http_code}" http://localhost:8000/
```

## Build Pipeline

```
npm run build         → Build static export
npm run verify        → Verify output is complete
npm run build:production → Build + verify
npm run clean         → Remove build artifacts
npm run deploy        → Full build → verify → deploy
```

## Production Checklist

- [ ] Set `NEXT_PUBLIC_API_URL` to production URL
- [ ] Set `NEXT_PUBLIC_WS_URL` to production WebSocket URL
- [ ] Build web UI: `npm run build:production`
- [ ] Configure reverse proxy (SSL, WebSocket upgrade)
- [ ] Verify `/api/health` returns 200
- [ ] Verify WebSocket connections work
- [ ] Test authentication flow
- [ ] Run Lighthouse audit
