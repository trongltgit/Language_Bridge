# Browser walkthrough tests (optional, manual)
Drive the real UI in jsdom against a running server on a fresh SQLite DB.
```bash
cd tests/ui && npm init -y && npm i jsdom ws
# terminal 1 (from backend/): ADMIN_PASSWORD=admin-password-123 DATABASE_URL=sqlite:////tmp/t.db uvicorn app.main:app --port 8765
node walkthrough.js      # admin, user, translator, guest, live captions, billing (needs a fresh DB)
# restart the server with a fresh DB, then:
node documents.js        # upload, translator edit, QA, approve, deliver
```
