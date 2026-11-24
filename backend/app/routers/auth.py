import secrets
import pyotp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..db import get_db, audit
from ..models import User, Job, SessionLine
from ..security import hash_pw, verify_pw, make_token, check_strength, throttle, note_fail, clear_fail, current_user
r = APIRouter(prefix="/auth", tags=["auth"])
class LoginIn(BaseModel): email: str; password: str; otp: str | None = None
class InviteIn(BaseModel): token: str; password: str
@r.post("/login")
def login(b: LoginIn, db=Depends(get_db)):
    key = b.email.lower(); throttle(key)
    u = db.query(User).filter(User.email == key).first()
    if not u or u.status != "active" or not verify_pw(u.pw_hash, b.password):
        note_fail(key); raise HTTPException(401, "Invalid credentials")
    if u.mfa_secret and not pyotp.TOTP(u.mfa_secret).verify(b.otp or "", valid_window=1):
        note_fail(key); raise HTTPException(401, "Invalid or missing one-time code")
    clear_fail(key); audit(db, u.public_id, "login")
    return {"access_token": make_token(u), "role": u.role, "id": u.public_id, "mfa_enrolled": bool(u.mfa_secret)}
@r.post("/accept-invite")
def accept(b: InviteIn, db=Depends(get_db)):
    """Admin never knows passwords: the person sets their own via the one-time invite token."""
    check_strength(b.password)
    u = db.query(User).filter(User.invite_token == b.token).first()
    if not u or not b.token: raise HTTPException(404, "Invalid or used invite")
    u.pw_hash = hash_pw(b.password); u.invite_token = None
    if u.status == "invited": u.status = "active"
    out = {"id": u.public_id, "status": u.status}
    if u.role in ("admin", "translator"):
        u.mfa_secret = pyotp.random_base32()
        out.update(mfa_secret=u.mfa_secret, mfa_uri=pyotp.TOTP(u.mfa_secret).provisioning_uri(name=u.email, issuer_name="LinguaBridge"))
    db.commit(); audit(db, u.public_id, "invite_accepted"); return out
@r.post("/mfa/setup")
def mfa_setup(u: User = Depends(current_user), db=Depends(get_db)):
    if u.mfa_secret: raise HTTPException(409, "MFA already enrolled")
    u.mfa_secret = pyotp.random_base32(); db.commit()
    return {"mfa_secret": u.mfa_secret, "mfa_uri": pyotp.TOTP(u.mfa_secret).provisioning_uri(name=u.email, issuer_name="LinguaBridge")}
@r.get("/me")
def me(u: User = Depends(current_user)): return {"id": u.public_id, "name": u.name, "email": u.email, "role": u.role, "region": u.region, "mfa_enrolled": bool(u.mfa_secret)}
@r.post("/erase-me")
def erase(u: User = Depends(current_user), db=Depends(get_db)):
    """Data-subject erasure (GDPR / Vietnam PDPL). Ledger rows stay (tax law); personal content is removed."""
    for j in db.query(Job).filter(Job.user_id == u.id): j.source_text = ""; j.final_text = ""
    u.email = f"erased-{u.public_id}@invalid"; u.name = "Erased"; u.pw_hash = None; u.mfa_secret = None; u.status = "erased"
    db.commit(); audit(db, u.public_id, "erasure"); return {"ok": True}
