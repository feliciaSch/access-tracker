# Access Tracker

A small internal tool for requesting and approving access to systems. The app is deliberately simple; the focus is on deployment, infrastructure and monitoring.

**Live app:** https://access-tracker-beta.vercel.app  ·  **API:** https://access-tracker-api.onrender.com (`/docs` for interactive API docs, `/health` for status)

## Architecture

```
 Browser (React SPA)
     │  HTTPS + JSON, Authorization: Bearer <JWT>
     ▼
 Vercel CDN ── serves the static frontend build (HTML/JS/CSS)
     │
     │  fetch() calls to VITE_API_URL
     ▼
 Render web service ── FastAPI (Python) ──► Neon Postgres (managed, TLS)
     │                  │
     │                  ├── JSON logs to stdout ──► Render log viewer
     │                  └── exceptions ──────────► Sentry
     ▼
 GitHub ── push triggers: Actions CI (lint/test/build/audit), CodeQL, Dependabot,
           and auto-deploys on Render + Vercel
```

| Piece | Tech | Where |
|---|---|---|
| Frontend | React 18 + Vite | Vercel (Hobby, free) |
| Backend | FastAPI, SQLAlchemy, Pydantic | Render (free web service) |
| Database | Postgres | Neon (free) |
| Auth | Username + bcrypt-hashed password, signed JWT (HS256) | backend |
| Monitoring | Structured JSON logs with request IDs, `/health`, Sentry | Render logs, Sentry |
| CI / security | GitHub Actions, pip-audit, npm audit, CodeQL, Dependabot | GitHub |

## Data model

- `users` — username, bcrypt password hash, role (`requester` or `approver`)
- `access_requests` — requester, resource, access_level (`read`/`write`/`admin`), justification, status (`pending`/`approved`/`denied`)
- `audit_events` — one append-only row per creation or status change: old → new status, who, when, note

A status change and its audit row are written in **one database transaction**, so history can't drift from the current state.

## API

| Method | Path | Who | What |
|---|---|---|---|
| GET | `/health` | anyone | App + DB check (503 if DB is down) |
| POST | `/auth/register` | anyone | Create a requester account |
| POST | `/auth/login` | anyone | Returns a JWT |
| GET | `/requests?status=&q=&resource=&mine=` | logged in | List and filter |
| POST | `/requests` | logged in | Submit a request |
| GET | `/requests/{id}` | logged in | One request |
| PATCH | `/requests/{id}/status` | approver | Approve / deny (writes audit row) |
| GET | `/requests/{id}/audit` | logged in | Audit trail |
| GET | `/debug/error` | anyone | Deliberate crash for the monitoring demo |

## Observability

Every request gets an `X-Request-ID` (generated, or taken from the incoming header). It's attached to **every log line** written while handling that request, returned in the response header, tagged on Sentry events, and shown in the app's footer, so one ID traces a click through the browser, the logs and Sentry.

Example log line:
```json
{"ts":"…","level":"INFO","msg":"access_request_status_changed","request_id":"5d9d0d98e392","access_request_id":1,"old_status":"pending","new_status":"denied","actor":"admin"}
```

## Run locally (optional)

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
ADMIN_PASSWORD=localpass123 uvicorn app.main:app --reload   # uses SQLite locally
pytest

# frontend (in another terminal)
cd frontend && npm install && npm run dev                   # http://localhost:5173
```

## Configuration

Backend (Render → Environment): `DATABASE_URL`, `ALLOWED_ORIGINS`, `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SENTRY_DSN`, `ENABLE_DEBUG_ROUTES`.
Frontend (Vercel → Environment Variables): `VITE_API_URL` (baked in at build time, so redeploy after changing it).

See `.env.example` files for formats.
