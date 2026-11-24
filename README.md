# LinguaBridge

Human + AI translation and interpreting platform. Roles: **Admin**, **User**, **Translator**, plus a no-account **Guest** (doctor, lawyer) who joins by one-time link. Flagship pair Vietnamese-English; more pairs are added from the admin screen.

**Status: complete test build.** Backend (FastAPI + Postgres), web UI, tests and Render deploy config are included and verified together. Payments are simulated and several production items are not built; see `docs/PRODUCTION.md` before real users or real money.

## Repo layout
```
backend/app/        API, policy engine, AI gateway, billing, models
backend/tests/      pytest (API flow, consent, MFA, billing, retention paths)
frontend/index.html web UI (single file, talks to the API)
tests/ui/           optional browser walkthrough tests
docs/               PRODUCTION.md (advice) and ui-prototype.html (early design mock)
Dockerfile  docker-compose.yml  render.yaml  .env.example  .github/workflows/ci.yml
```

## Run locally
```bash
cp .env.example .env     # set JWT_SECRET (32+ chars) and ADMIN_PASSWORD (12+ chars)
docker compose up --build    # http://localhost:8000  (API docs at /docs)
# or without Docker (SQLite):
cd backend && pip install -r requirements.txt && ADMIN_PASSWORD='choose-a-long-passphrase' uvicorn app.main:app --reload
cd backend && pytest         # 2 tests
```

## Put it on GitHub, then deploy on Render
```bash
git init && git add . && git commit -m "LinguaBridge test build"
git branch -M main && git remote add origin https://github.com/YOU/linguabridge.git && git push -u origin main
```
1. Render dashboard: **New > Blueprint**, pick the repo. Render reads `render.yaml` and creates the web service and a Postgres database.
2. When prompted, set `ADMIN_EMAIL`, `ADMIN_PASSWORD` (12+ chars) and optionally `ANTHROPIC_API_KEY`. `JWT_SECRET` and `DATABASE_URL` are filled automatically.
3. Wait for the build, open the service URL, sign in as the admin.

**Free-tier behavior to expect (per Render's docs):** a free web service spins down after 15 minutes without traffic and takes about a minute to wake; the filesystem is ephemeral (fine, all data is in Postgres); a free Postgres database expires 30 days after creation. Fine for testing, not for anything you want to keep.

## Test checklist (15 minutes)
1. **Admin:** Accounts > create a *translator* (pairs `vi-en`, domains `General,Business`) and a *user*. Copy each invite link.
2. Open each invite link in a private window, set a password. The translator gets an MFA secret: add it to an authenticator app.
3. **User:** Plan > subscribe. New translation > upload a `.txt` or `.docx` > quote > pay. Jobs shows only status until approval.
4. **Translator** (sign in with the app code): Job queue > Accept > edit > Run AI QA > Approve. Earnings shows the net after commission.
5. **User:** Jobs > Get result. Admin > Ledger shows charge, commission, pending payout.
6. **Interpreting:** User > Interpreting > start (General). Copy the guest link from Sessions, open it in another browser. Translator > Sessions > Open. When all three are connected, type lines (or use Mic in Chrome) and watch captions. End the session: 15-minute minimum is billed.
7. **Compliance:** Admin > Credentials: a Medical or Immigration job is not offered to the translator until you record a verified credential. Admin > Tools > break-glass requires a reason and appears in the audit log. Medical sessions in the US block AI until `AI_VENDOR_BAA=true`.
Without `ANTHROPIC_API_KEY`, AI drafts are skipped and translators work from the source text (the rest of the flow is identical).

## What is verified
Backend pytest passes. Browser walkthroughs (`tests/ui`) pass against a live server: admin, user, translator and guest roles, invites, MFA login, subscription, quote/pay, translator edit/QA/approve, result delivery, consented live session with captions between three participants, session billing and commission. Not verified: Docker build and Render deploy (could not run here), real AI output (needs your API key), real audio.

## Known limits of this build
Payments simulated; money stored as floats; live rooms live in one process (single instance only); AI drafts run inside the request; no email sending; JWT kept in sessionStorage; schema created with `create_all`. All are addressed in `docs/PRODUCTION.md`.
