# Mapster Outreach (MERN)

React (Vite, TypeScript) + Express + MongoDB + BullMQ/Redis. One container serves the API and the built UI.

## Run with Docker (production)
```
cp .env.example .env     # set JWT_SECRET, ADMIN_*, GMAIL_APP_PASSWORD, ANTHROPIC_API_KEY
docker compose up -d --build
```
Open http://localhost:8080 and sign in with ADMIN_EMAIL / ADMIN_PASSWORD. Put it behind HTTPS (Caddy, nginx or your host's proxy) before exposing it.

## Develop
Start MongoDB and Redis (`docker compose up -d mongo redis`), then:
```
cd server && cp ../.env.example .env && npm run dev      # API + worker on :8080
cd client && npm run dev                                 # UI on :5173, proxies /api
```
Checks: `npm run typecheck && npm test` (server), `npm run build` (client).
Import the old Python data once: `cd server && npm run migrate:legacy`.

## How it works
- `Contact` is one Mongo document per recipient (details plus outreach state).
- Every send, draft and test is a BullMQ job. Sends are spaced 90 to 240 s apart, survive restarts, and retry on failure.
- A contact is atomically claimed (`sending` flag) before SMTP, so a retry can never double send.
- Autopilot is a repeatable job that checks replies and bounces over IMAP, then queues approved emails and due follow ups inside the sending window.
- Auth is a JWT in an httpOnly, SameSite=strict cookie. Login is rate limited. Helmet sets security headers.
- PDFs are rendered with Chromium (puppeteer-core) and cached per name.
