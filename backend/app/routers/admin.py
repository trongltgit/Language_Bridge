import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from ..db import get_db, audit, set_setting, get_setting
from ..config import settings
from ..models import User, TranslatorProfile, Credential, LanguagePair, Ledger, Audit, Job
from ..security import require
from .. import policy
r = APIRouter(prefix="/admin", tags=["admin"])
A = Depends(require("admin"))
class NewUser(BaseModel):
    name: str; email: str; role: str; region: str = "US"; pairs: list[str] = []; domains: list[str] = []
class Cred(BaseModel): user_public_id: str; type: str; number: str; expires_at: datetime
class Pair(BaseModel): word_rate: float | None = None; min_rate: float | None = None; status: str | None = None; name: str | None = None
class Fees(BaseModel): commission_pct: float | None = None; membership_usd: float | None = None
class Reason(BaseModel): reason: str
def _by_pid(db, pid):
    u = db.query(User).filter(User.public_id == pid).first()
    if not u: raise HTTPException(404, "No such account")
    return u
@r.post("/users")
def create_user(b: NewUser, a=A, db=Depends(get_db)):
    if b.role not in ("user", "translator"): raise HTTPException(422, "role must be user or translator")
    if db.query(User).filter(User.email == b.email.lower()).first(): raise HTTPException(409, "Email already registered")
    n = db.query(func.count(User.id)).filter(User.role == b.role).scalar() + 1
    u = User(public_id=("US-" if b.role == "user" else "TR-") + f"{n:04d}", email=b.email.lower(), name=b.name, role=b.role,
             region=b.region, invite_token=secrets.token_urlsafe(32), status="invited")
    db.add(u); db.commit()
    if b.role == "translator": db.add(TranslatorProfile(user_id=u.id, pairs=b.pairs, domains=b.domains)); db.commit()
    audit(db, a.public_id, "create_user", u.public_id)
    return {"id": u.public_id, "invite_token": u.invite_token, "note": "Send as a one-time link. Person sets their own password."}
@r.get("/users")
def users(a=A, db=Depends(get_db)):
    return [{"id": u.public_id, "name": u.name, "email": u.email, "role": u.role, "status": u.status, "region": u.region} for u in db.query(User)]
@r.post("/users/{pid}/status")
def set_status(pid: str, status: str, a=A, db=Depends(get_db)):
    if status not in ("active", "suspended"): raise HTTPException(422, "status must be active or suspended")
    u = _by_pid(db, pid)
    if u.role == "admin": raise HTTPException(403, "Cannot change an admin here")
    if u.status == "invited": raise HTTPException(409, "Account has not accepted its invite yet")
    u.status = status; db.commit(); audit(db, a.public_id, "set_status", f"{pid}:{status}"); return {"id": pid, "status": status}
@r.post("/users/{pid}/reset")
def reset(pid: str, a=A, db=Depends(get_db)):
    u = _by_pid(db, pid); u.invite_token = secrets.token_urlsafe(32); u.pw_hash = None; u.mfa_secret = None; db.commit()
    audit(db, a.public_id, "force_reset", pid); return {"invite_token": u.invite_token}
@r.post("/credentials")
def add_cred(b: Cred, a=A, db=Depends(get_db)):
    u = _by_pid(db, b.user_public_id)
    c = Credential(user_id=u.id, type=b.type.upper(), number=b.number, expires_at=b.expires_at, verified=True)
    db.add(c); db.commit(); audit(db, a.public_id, "verify_credential", f"{b.user_public_id}:{b.type}"); return {"ok": True}
@r.put("/pairs/{pid}")
def edit_pair(pid: str, b: Pair, a=A, db=Depends(get_db)):
    import re
    if not re.fullmatch(r"[a-z]{2,3}-[a-z]{2,3}", pid): raise HTTPException(422, "pair id must look like vi-en")
    p = db.get(LanguagePair, pid)
    if not p:
        if not (b.name and b.word_rate and b.min_rate): raise HTTPException(422, "name, word_rate, min_rate required for a new pair")
        p = LanguagePair(id=pid, name=b.name, word_rate=b.word_rate, min_rate=b.min_rate, status="PLANNED"); db.add(p)
    for k in ("word_rate", "min_rate", "status", "name"):
        v = getattr(b, k)
        if v is not None: setattr(p, k, v)
    db.commit(); audit(db, a.public_id, "edit_pair", f"{pid}:{b.status or ''}"); return {"ok": True}
@r.put("/fees")
def fees(b: Fees, a=A, db=Depends(get_db)):
    if b.commission_pct is not None:
        if not 0 <= b.commission_pct <= 50: raise HTTPException(422, "commission 0-50")
        set_setting(db, "commission_pct", b.commission_pct)
    if b.membership_usd is not None: set_setting(db, "membership_usd", b.membership_usd)
    audit(db, a.public_id, "set_fees", b.model_dump_json()); return {"commission_pct": get_setting(db, "commission_pct", settings.COMMISSION_PCT)}
@r.get("/ledger")
def ledger(a=A, db=Depends(get_db)):
    return [{"ts": x.ts, "type": x.type, "ref": x.ref, "account": x.account, "amount": x.amount} for x in db.query(Ledger).order_by(Ledger.id.desc()).limit(500)]
@r.get("/reports/revenue")
def revenue(a=A, db=Depends(get_db)):
    s = lambda t: db.query(func.coalesce(func.sum(Ledger.amount), 0)).filter(Ledger.type == t).scalar()
    return {"subscriptions": s("SUBSCRIPTION"), "commission": s("COMMISSION"), "user_charges": s("USER_CHARGE"), "payouts_pending": s("PAYOUT_PENDING")}
@r.get("/audit")
def audit_log(a=A, db=Depends(get_db)):
    return [{"ts": x.ts, "actor": x.actor, "action": x.action, "detail": x.detail} for x in db.query(Audit).order_by(Audit.id.desc()).limit(500)]
@r.post("/break-glass/jobs/{jid}")
def break_glass(jid: int, b: Reason, a=A, db=Depends(get_db)):
    """Admins cannot read content normally. A reason is mandatory and permanently logged."""
    if len(b.reason.strip()) < 10: raise HTTPException(422, "Give a specific reason (10+ characters)")
    j = db.get(Job, jid)
    if not j: raise HTTPException(404, "No such job")
    audit(db, a.public_id, "BREAK_GLASS_READ", f"job {jid}: {b.reason}"); return {"source_text": j.source_text, "final_text": j.final_text}
@r.post("/retention/run")
def retention(a=A, db=Depends(get_db)):
    out = policy.purge(db); audit(db, a.public_id, "retention_run", str(out)); return out
@r.get("/policy/{domain}/{country}")
def show_policy(domain: str, country: str, a=A): return policy.evaluate(domain, country.upper())
