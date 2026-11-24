# From test deploy to production

Work in this order. Items marked **blocker** should be finished before real users; **legal** items need qualified counsel in each market.

## 1. Fix the known shortcuts in this build
| Item | Why it matters | Do this |
|---|---|---|
| **Money as floats** (blocker) | Rounding errors in a ledger | Store integer minor units (cents, VND) or `Decimal`; add currency to every row; reconcile against the payment provider |
| **Simulated payments** (blocker) | No real revenue or payouts | Stripe (US cards, Connect for translator payouts), VNPay/MoMo/ZaloPay (VN). Use webhooks for truth, idempotency keys, escrow-style holds until approval, refunds and clawbacks, tax and Vietnamese e-invoices |
| **Live rooms in memory** (blocker for >1 instance) | A second server instance cannot see the first's WebSocket rooms | Redis pub/sub (or move captions onto LiveKit data channels) before scaling out |
| **AI drafts inside the request** | Large documents will hit timeouts | Move to a worker queue (Redis + RQ/Arq/Celery); show progress; retry with backoff; per-user AI spend caps |
| **`create_all` schema** (blocker) | No safe upgrades | Add Alembic migrations, run them as a release step, never auto-create in production |
| **Files stored as text in the DB** | No scans, layout, or encryption control | S3-compatible object storage with per-file encryption and signed URLs, virus scanning, OCR for images/scans, layout-preserving DOCX/PDF output |
| **Login throttle in memory** | Resets on restart, per instance | Persist in Redis; add rate limiting at the edge (Cloudflare or your gateway) |
| **JWT in sessionStorage, token in WebSocket URL** | XSS can steal it; URLs end up in logs | httpOnly Secure SameSite cookies (add CSRF protection) or short-lived tokens with refresh; WebSocket auth with a one-time ticket instead of the token in the URL |
| **No password reset or email** | Support burden, weak recovery | Transactional email (SES/Postmark), reset and verification flows, MFA recovery codes, optional SSO for business accounts |
| **Admin can create but not review translators' test work** | Quality risk | Onboarding tests, second-reviewer step for legal/medical, ratings and dispute workflow |

## 2. Hosting
- **Render is fine for a pilot** if you pay for what matters: a non-free web instance (no spin-down), a paid Postgres plan (the free database expires and has no backups), and Render's backup/point-in-time recovery features on paid plans. Confirm current plan names and limits on Render's pricing page.
- **Region = data residency.** Pick the region by where the people whose data you hold live. Vietnamese residents' data triggers cross-border-transfer duties under Vietnam's PDPL; US health data triggers HIPAA. You may need separate US and Vietnam deployments with data kept in-region.
- **Medical (HIPAA) needs a BAA with every vendor touching PHI**: host, database, AI, speech recognition, email, telephony, error tracking. Render may not offer one on every plan; if you cannot get a BAA, move that workload to AWS/GCP/Azure (which offer them) before handling PHI. Keep `AI_VENDOR_BAA=false` until the AI vendor's agreement is signed and zero-retention is configured.
- Put the app behind a CDN/WAF (Cloudflare), keep secrets in the platform secret store, rotate `JWT_SECRET`, restrict database network access.
- Backups with tested restores; encryption at rest; an incident runbook with notification clocks per jurisdiction.

## 3. Real-time interpreting, properly
- LiveKit Cloud or self-hosted (token endpoint already in the API) for 3-party audio/video; TURN for restrictive networks.
- Streaming speech recognition with Vietnamese dialect testing; measure word-error rate on medical and legal speech before trusting captions.
- **Phone dial-in** (Twilio, Telnyx or a local VN carrier): most elderly users will use this, so it is likely your biggest adoption lever. Add call recording consent scripts per state.
- Reconnect handling and billing pause; scheduled sessions with reminders (email, SMS, Zalo); interpreter on-call rotas across US and VN time zones.

## 4. Security and operations
- Penetration test and dependency scanning (Dependabot, `pip-audit`) in CI; SAST; secret scanning.
- Application-level encryption for `source_text` and `final_text` with a KMS-managed key; per-tenant keys for business customers.
- Structured logs with **no document text, transcripts, or tokens**; Sentry with data scrubbing; uptime and latency alerts; AI cost dashboards.
- Load test the WebSocket path and document upload before launch.

## 5. Legal and compliance (legal)
Get counsel in the US and Vietnam before enabling medical, legal or immigration work. Checklist:
- **Vietnam:** PDPL (in force 1 Jan 2026) and its implementing decree: consent, data-subject rights, data protection impact assessments, cross-border transfer assessments filed with the authorities. The AI Law (in force 1 Mar 2026): risk classification of your system, AI disclosure, incident handling; a new platform should assume no grace period. E-invoices, VAT, foreign-contractor tax rules, notarization rules for certified translations.
- **US:** HIPAA business-associate status and BAAs; ACA Section 1557 (qualified interpreters; human review of machine translation) for healthcare customers; state recording-consent laws; Title VI for public programs; state court-interpreter certification; USCIS translation-certification format; independent-contractor classification by state; 1099 reporting; state privacy laws; subscription auto-renewal rules.
- **Everywhere:** Terms of Service, Privacy Policy, interpreter agreement with NDA and code of ethics, "not legal or medical advice" notices, professional liability (E&O) and cyber insurance, sanctions screening and payout KYC.
- The rule set in `policy.py` is a starting point. Treat each change as a versioned, reviewed release.

## 6. Launch sequence
1. **Private pilot (weeks 1-4):** Render paid tier, General/Business documents only, 2-5 vetted translators, real payments in test mode, no medical or legal.
2. **Paid pilot:** real payments (Stripe or VNPay), email, worker queue, object storage, Alembic, monitoring, backups. Collect translator and user feedback.
3. **Interpreting beta:** LiveKit, ASR, phone dial-in, scheduled sessions; General and Business first.
4. **Regulated domains, one at a time:** Immigration (certified translations), then Legal, then Medical after BAAs, credential checks, and counsel sign-off. Consider a hospital B2B pilot, which is also a revenue channel.
5. **Scale:** add language pairs through the admin registry only after interpreters, glossary, and AI quality checks meet your launch checklist; pursue SOC 2 / ISO 27001, ISO 17100 and ISO 18841 as enterprise customers ask.

## 7. Business risks worth watching
Interpreter supply in off-hours and rare pairs; unit economics (AI plus interpreter cost per minute vs price); disputes and refunds; reliance on a single AI vendor (the gateway in `ai.py` is built to swap); the hybrid fee model discouraging translators in thin pairs (waive fees there).
