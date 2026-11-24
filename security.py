import time
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import settings
from .db import get_db
from .models import User
_ph = PasswordHasher(); bearer = HTTPBearer(auto_error=False)
def hash_pw(p): return _ph.hash(p)
def verify_pw(h, p):
    try: return bool(h) and _ph.verify(h, p)
    except Exception: return False
def check_strength(p):
    if len(p) < 12: raise HTTPException(422, "Password must be at least 12 characters")
def make_token(u):
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_MINUTES)
    return jwt.encode({"sub": str(u.id), "role": u.role, "exp": exp}, settings.JWT_SECRET, "HS256")
_fails = {}
def throttle(key):
    n, t0 = _fails.get(key, (0, time.time()))
    if time.time() - t0 > 900: _fails.pop(key, None); return
    if n >= 5: raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
def note_fail(key):
    n, t0 = _fails.get(key, (0, time.time())); _fails[key] = (n + 1, t0)
def clear_fail(key): _fails.pop(key, None)
def current_user(request: Request, creds: HTTPAuthorizationCredentials = Depends(bearer), db=Depends(get_db)):
    if not creds: raise HTTPException(401, "Not authenticated")
    try: data = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401, "Invalid or expired token")
    u = db.get(User, int(data["sub"]))
    if not u or u.status != "active": raise HTTPException(403, "Account is not active")
    if settings.REQUIRE_MFA and u.role in ("admin", "translator") and not u.mfa_secret and not request.url.path.startswith("/auth/"):
        raise HTTPException(403, "MFA enrollment required: call /auth/mfa/setup")
    return u
def require(*roles):
    def dep(u: User = Depends(current_user)):
        if u.role not in roles: raise HTTPException(403, "Forbidden for this role")
        return u
    return dep
