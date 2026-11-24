import os, tempfile
d = tempfile.mkdtemp(); os.environ.update(DATABASE_URL=f"sqlite:///{d}/t.db", ADMIN_PASSWORD="admin-password-123", JWT_SECRET="test")
from datetime import datetime, timedelta
import pyotp
from fastapi.testclient import TestClient
from app.main import app
def H(t): return {"Authorization": f"Bearer {t}"}
def test_full_flow():
    with TestClient(app) as c:
        adm = c.post("/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"}).json()["access_token"]
        u = c.post("/admin/users", headers=H(adm), json={"name": "Lan", "email": "lan@x.com", "role": "user", "region": "US"}).json()
        t = c.post("/admin/users", headers=H(adm), json={"name": "Minh", "email": "minh@x.com", "role": "translator", "pairs": ["vi-en"], "domains": ["General", "Immigration"]}).json()
        c.post("/auth/accept-invite", json={"token": u["invite_token"], "password": "user-password-123"}).raise_for_status()
        mfa = c.post("/auth/accept-invite", json={"token": t["invite_token"], "password": "translator-pass-123"}).json()["mfa_secret"]
        assert c.post("/auth/accept-invite", json={"token": "bad", "password": "x" * 12}).status_code == 404
        ut = c.post("/auth/login", json={"email": "lan@x.com", "password": "user-password-123"}).json()["access_token"]
        assert c.post("/auth/login", json={"email": "minh@x.com", "password": "translator-pass-123"}).status_code == 401  # MFA needed
        tt = c.post("/auth/login", json={"email": "minh@x.com", "password": "translator-pass-123", "otp": pyotp.TOTP(mfa).now()}).json()["access_token"]
        f = {"file": ("a.txt", "Sinh ngày 12/03/2015 tại Hà Nội".encode(), "text/plain")}
        assert c.post("/jobs", headers=H(ut), data={"pair_id": "vi-en", "domain": "General"}, files=f).status_code == 402   # needs subscription
        c.post("/billing/subscribe?plan=Pro", headers=H(ut)).raise_for_status()
        j = c.post("/jobs", headers=H(ut), data={"pair_id": "vi-en", "domain": "Immigration"}, files=f).json()
        c.post(f"/jobs/{j['id']}/pay", headers=H(ut)).raise_for_status()
        assert c.get(f"/jobs/{j['id']}/result", headers=H(ut)).status_code == 409      # hidden before approval
        assert c.get("/jobs", headers=H(tt)).json() == []                              # no verified credential yet
        assert c.post(f"/jobs/{j['id']}/accept", headers=H(tt)).status_code == 403
        c.post("/admin/credentials", headers=H(adm), json={"user_public_id": t["id"], "type": "ATA", "number": "1", "expires_at": (datetime.utcnow() + timedelta(days=300)).isoformat()}).raise_for_status()
        q = c.get("/jobs", headers=H(tt)).json(); assert q[0]["you_earn"] == round(q[0]["value"] * .8, 2)
        c.post(f"/jobs/{j['id']}/accept", headers=H(tt)).raise_for_status()
        assert c.post(f"/jobs/{j['id']}/approve", headers=H(tt)).status_code == 409    # QA required
        c.put(f"/jobs/{j['id']}/draft", headers=H(tt), json={"text": "Born 12/03/2015 in Hanoi"}).raise_for_status()
        assert c.post(f"/jobs/{j['id']}/qa", headers=H(tt)).json()["flags"] == []
        c.post(f"/jobs/{j['id']}/approve", headers=H(tt)).raise_for_status()
        res = c.get(f"/jobs/{j['id']}/result", headers=H(ut)).json()
        assert "Hanoi" in res["text"] and "Certification" in res["certificate"]
        rev = c.get("/admin/reports/revenue", headers=H(adm)).json(); assert rev["commission"] > 0 and rev["subscriptions"] == 29
        assert c.get(f"/jobs/{j['id']}/source", headers=H(adm)).status_code in (404, 405)
        assert c.post(f"/admin/break-glass/jobs/{j['id']}", headers=H(adm), json={"reason": "x"}).status_code == 422
        c.post(f"/admin/users/{u['id']}/status?status=suspended", headers=H(adm)).raise_for_status()
        assert c.get("/jobs", headers=H(ut)).status_code == 403                         # suspended
        c.post(f"/admin/users/{t['id']}/status?status=suspended", headers=H(adm)).raise_for_status()   # keep test 2 isolated
def test_session_flow():
    with TestClient(app) as c:
        adm = c.post("/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"}).json()["access_token"]
        u = c.post("/admin/users", headers=H(adm), json={"name": "U", "email": "u2@x.com", "role": "user"}).json()
        t = c.post("/admin/users", headers=H(adm), json={"name": "T", "email": "t2@x.com", "role": "translator", "pairs": ["vi-en"], "domains": ["General"]}).json()
        c.post("/auth/accept-invite", json={"token": u["invite_token"], "password": "user-password-123"})
        mfa = c.post("/auth/accept-invite", json={"token": t["invite_token"], "password": "translator-pass-123"}).json()["mfa_secret"]
        ut = c.post("/auth/login", json={"email": "u2@x.com", "password": "user-password-123"}).json()["access_token"]
        tt = c.post("/auth/login", json={"email": "t2@x.com", "password": "translator-pass-123", "otp": pyotp.TOTP(mfa).now()}).json()["access_token"]
        c.post("/billing/subscribe?plan=Basic", headers=H(ut))
        body = {"pair_id": "vi-en", "domain": "General", "country": "US"}
        assert c.post("/sessions", headers=H(ut), json={**body, "consents": ["transcription"]}).status_code == 422   # consent missing
        s = c.post("/sessions", headers=H(ut), json={**body, "consents": ["transcription", "ai_processing"]}).json()
        sid = s["id"]; assert c.post(f"/sessions/{sid}/join", json={"consent": False}).status_code == 422
        c.post(f"/sessions/{sid}/join", headers=H(ut), json={"consent": True})
        c.post(f"/sessions/{sid}/join", headers=H(tt), json={"consent": True})
        assert c.post(f"/sessions/{sid}/join", json={"consent": True, "guest_token": "wrong"}).status_code == 403
        j = c.post(f"/sessions/{sid}/join", json={"consent": True, "guest_token": s["guest_link_token"]}).json(); assert j["billing_started"]
        with c.websocket_connect(f"/ws/sessions/{sid}?token={ut}") as w1, c.websocket_connect(f"/ws/sessions/{sid}?token={s['guest_link_token']}") as w2:
            w1.send_json({"text": "Tôi bị đau 2 ngày", "lang": "vi"}); m = w2.receive_json()
            assert m["type"] == "caption" and m["ai_generated"] and m["texts"]["vi"].startswith("Tôi")
        e = c.post(f"/sessions/{sid}/end", headers=H(ut)).json(); assert e["minutes_billed"] == 15     # minimum billing
