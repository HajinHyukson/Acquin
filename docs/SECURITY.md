# Security Review (Phase 5)

Status: **initial review for the MVP**. This is a self-hosted analytics backend
with no end-user authentication yet. Re-review before any public/commercial
deployment.

## Implemented

- **Input validation**: all request bodies/queries are validated by Pydantic
  models / typed FastAPI params; unknown fields are ignored, types coerced.
- **SQL injection**: all DB access goes through SQLAlchemy Core/ORM with bound
  parameters — no string-built SQL.
- **Error envelope**: errors return a structured `{error:{code,message}}` body
  without stack traces (tracebacks are logged server-side only).
- **CORS**: configurable via `KOSPI_CORS_ORIGINS` (default `*` for local dev —
  set explicit origins in production).
- **Secrets**: no secrets in code; configuration via env vars / `.env` (which is
  git-ignored). Webhook URLs and DB credentials come from the environment.
- **Container**: runs from a slim base image; `.dockerignore` keeps source-only
  content out; data lives on a mounted volume.

## Open items before production

| Item | Action |
|---|---|
| Authentication / authorization | Add API auth (API keys or OAuth) before exposing publicly; watchlists are currently unscoped (no per-user isolation). |
| CORS | Replace `*` with an explicit allow-list. |
| Rate limiting | Add a reverse-proxy or middleware rate limiter. |
| Webhook SSRF | Restrict `KOSPI_ALERT_WEBHOOK_URL` to a trusted host allow-list. |
| TLS | Terminate TLS at a reverse proxy (nginx/traefik); do not expose uvicorn directly. |
| DB hardening | Move off SQLite to PostgreSQL with least-privilege credentials and network restrictions. |
| Dependency scanning | Add `pip-audit`/Dependabot to CI. |
| Logging/PII | No PII is stored today; revisit if user accounts are added. |
| Model artifacts | `joblib` files are trusted inputs — load only artifacts you produced (pickle deserialization risk). |

## Notes

- The `sample` data provider is synthetic; the `pykrx` provider performs
  outbound HTTP to public endpoints. Confirm egress policy in production.
- ML predictions are advisory and surfaced with an uncertainty disclaimer; they
  must not be presented as guaranteed prices (see context doc §19.3).
