import asyncio, secrets, time
from datetime import datetime
import jwt
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel
from ..config import settings
from ..db import get_db, audit, SessionLocal
from ..models import InterpSession, User, TranslatorProfile, LanguagePair, Consent, SessionLine
from ..security import require, current_user, bearer
from .jobs import active_sub
from .. import ai, billing, policy
r = APIRouter(tags=["interpreting"])
class NewSession(BaseModel): pair_id: str; domain: str; country: str = "US"; consents: list[str]
class JoinIn(BaseModel): consent: bool; guest_token: str | None = None
def _sess(db, sid):
    s = db.get(InterpSession, sid)
    if not s: raise HTTPException(404, "No such session")
    return s
@r.post("/sessions")
def create(b: NewSession, u: User = Depends(require("user")), db=Depends(get_db)):
    active_sub(db, u)
    pol = policy.evaluate(b.domain, b.country)
    if b.domain not in billing.MULT: raise HTTPException(422, "Unknown domain")
    missing = [c for c in pol["consents_required"] if c not in b.consents]
    if missing: raise HTTPException(422, f"Consent required: {missing}")
    p = db.get(LanguagePair, b.pair_id)
    if not p or p.status != "LIVE": raise HTTPException(422, "Language pair not available")
    tr = next((t for t in db.query(User).filter(User.role == "translator", User.status == "active")
               if (db.get(TranslatorProfile, t.id) or TranslatorProfile(available=False)).available and policy.translator_ok(db, t, b.pair_id, b.domain)), None)
    if not tr: raise HTTPException(409, "No qualified interpreter available. Try scheduling for later.")
    s = InterpSession(user_id=u.id, translator_id=tr.id, pair_id=b.pair_id, domain=b.domain, country=b.country,
                      guest_token=secrets.token_urlsafe(24), joined={"user": False, "translator": False, "guest": False})
    db.add(s); db.commit()
    for c in b.consents: db.add(Consent(who=u.public_id, ref=f"S{s.id}", kind=c))
    db.commit(); audit(db, u.public_id, "session_created", f"{s.id} {b.domain} {b.country}")
    return {"id": s.id, "guest_link_token": s.guest_token, "interpreter": tr.public_id, "rate_per_min": billing.minute_rate(p, b.domain),
            "minimum_minutes": billing.MIN_MINUTES, "policy": pol}
def _role(db, s, creds, guest_token=None):
    if guest_token and secrets.compare_digest(guest_token, s.guest_token): return "guest"
    if creds:
        try: u = db.get(User, int(jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=["HS256"])["sub"]))
        except Exception: raise HTTPException(401, "Invalid token")
        if u and u.status == "active":
            if u.id == s.user_id: return "user"
            if u.id == s.translator_id: return "translator"
    return None
@r.post("/sessions/{sid}/join")
def join(sid: int, b: JoinIn, db=Depends(get_db), creds=Depends(bearer)):
    s = _sess(db, sid)
    if s.status != "OPEN": raise HTTPException(409, "Session ended")
    if not b.consent: raise HTTPException(422, "Consent is required to join")
    role = _role(db, s, creds, b.guest_token)
    if not role: raise HTTPException(403, "Not a participant")
    s.joined = {**s.joined, role: True}
    db.add(Consent(who=role, ref=f"S{sid}", kind="join"))
    if all(s.joined.values()) and not s.started_at: s.started_at = datetime.utcnow()   # billing starts when all connect
    db.commit(); return {"joined": s.joined, "billing_started": bool(s.started_at)}
@r.get("/sessions/{sid}")
def get_session(sid: int, guest_token: str | None = None, db=Depends(get_db), creds=Depends(bearer)):
    s = _sess(db, sid); role = _role(db, s, creds, guest_token)
    if not role: raise HTTPException(403, "Not a participant")
    return {"id": s.id, "role": role, "pair": s.pair_id, "langs": s.pair_id.split("-"), "domain": s.domain, "country": s.country, "status": s.status,
            "joined": s.joined, "started_at": s.started_at, "minutes_billed": s.minutes_billed, "policy": policy.evaluate(s.domain, s.country)}
@r.get("/sessions")
def my_sessions(u: User = Depends(require("user", "translator")), db=Depends(get_db)):
    col = InterpSession.user_id if u.role == "user" else InterpSession.translator_id
    out = []
    for s in db.query(InterpSession).filter(col == u.id).order_by(InterpSession.id.desc()).limit(50):
        row = {"id": s.id, "pair": s.pair_id, "domain": s.domain, "status": s.status, "minutes_billed": s.minutes_billed, "joined": s.joined}
        if u.role == "user" and s.status == "OPEN": row["guest_link_token"] = s.guest_token
        out.append(row)
    return out
@r.get("/sessions/{sid}/transcript")
def transcript(sid: int, u: User = Depends(require("user", "translator")), db=Depends(get_db)):
    s = _sess(db, sid)
    if u.id not in (s.user_id, s.translator_id): raise HTTPException(403, "Not a participant")
    rows = db.query(SessionLine).filter(SessionLine.session_id == sid).order_by(SessionLine.id).all()
    return [{"speaker": x.speaker, "texts": x.texts, "ts": x.ts} for x in rows]
@r.get("/translator/profile")
def tprofile(u: User = Depends(require("translator")), db=Depends(get_db)):
    p = db.get(TranslatorProfile, u.id); return {"pairs": p.pairs, "domains": p.domains, "available": p.available}
@r.put("/translator/availability")
def tavail(available: bool, u: User = Depends(require("translator")), db=Depends(get_db)):
    p = db.get(TranslatorProfile, u.id); p.available = available; db.commit(); return {"available": available}
@r.get("/sessions/{sid}/media-token")
def media(sid: int, u: User = Depends(current_user), db=Depends(get_db)):
    """LiveKit access token (HS256 JWT per LiveKit spec). Audio/video itself is handled by LiveKit, not this API."""
    s = _sess(db, sid)
    if u.id not in (s.user_id, s.translator_id): raise HTTPException(403, "Not a participant")
    if not settings.LIVEKIT_KEY: raise HTTPException(501, "LiveKit not configured")
    now = int(time.time())
    t = jwt.encode({"iss": settings.LIVEKIT_KEY, "sub": u.public_id, "nbf": now, "exp": now + 3600,
                    "video": {"room": f"lb-{sid}", "roomJoin": True, "canPublish": True, "canSubscribe": True}}, settings.LIVEKIT_SECRET, "HS256")
    return {"url": settings.LIVEKIT_URL, "token": t}
@r.post("/sessions/{sid}/end")
def end(sid: int, u: User = Depends(require("user", "translator")), db=Depends(get_db)):
    s = _sess(db, sid)
    if u.id not in (s.user_id, s.translator_id): raise HTTPException(403, "Not a participant")
    if s.status != "OPEN": raise HTTPException(409, "Already ended")
    s.ended_at = datetime.utcnow(); secs = int((s.ended_at - s.started_at).total_seconds()) if s.started_at else 0
    s.minutes_billed = billing.minutes_billed(secs, bool(s.started_at)); s.status = "ENDED"; db.commit()
    p = db.get(LanguagePair, s.pair_id); amt = round(s.minutes_billed * billing.minute_rate(p, s.domain), 2)
    if amt:
        tr = db.get(User, s.translator_id); user = db.get(User, s.user_id)
        billing.charge(user, amt, f"S{sid}"); billing.post(db, "USER_CHARGE", f"S{sid}", amt, user.public_id); billing.settle(db, f"S{sid}", amt, tr.public_id)
    audit(db, u.public_id, "session_ended", f"{sid} {s.minutes_billed}min {amt}"); return {"minutes_billed": s.minutes_billed, "amount_usd": amt}
rooms: dict = {}; last_user: dict = {}
@r.websocket("/ws/sessions/{sid}")
async def ws(websocket: WebSocket, sid: int, token: str):
    db = SessionLocal(); role = None
    try:
        s = db.get(InterpSession, sid)
        if s and s.status == "OPEN":
            if secrets.compare_digest(token, s.guest_token): role = "guest"
            else:
                try:
                    u = db.get(User, int(jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])["sub"]))
                    role = "user" if u.id == s.user_id else "translator" if u.id == s.translator_id else None
                    if u.status != "active": role = None
                except Exception: role = None
        if not role or not s.joined.get(role): await websocket.close(code=4403); return
        src, tgt = s.pair_id.split("-"); allow_ai = policy.ai_allowed(s.domain, s.country)
        keep = settings.TRANSCRIPT_RETENTION_DAYS > 0
        await websocket.accept(); rooms.setdefault(sid, []).append((websocket, role))
        while True:
            m = await websocket.receive_json(); text = str(m.get("text", ""))[:2000].strip()
            if not text: continue
            lang = m.get("lang") if m.get("lang") in (src, tgt) else (src if role == "user" else tgt)
            other = tgt if lang == src else src; texts = {lang: text}
            if allow_ai: texts[other] = await asyncio.to_thread(ai.translate_line, text, lang, other, s.domain)
            if keep: db.add(SessionLine(session_id=sid, speaker=role, texts=texts)); db.commit()
            msg = {"type": "caption", "speaker": role, "texts": texts, "ai_generated": True, "notice": policy.evaluate(s.domain, s.country)["ai_disclosure"]}
            if role == "user": last_user[sid] = text
            for conn, _ in list(rooms.get(sid, [])):
                try: await conn.send_json(msg)
                except Exception: pass
            if role == "translator" and sid in last_user:   # private assist: numbers the interpreter dropped
                miss = ai.omitted_numbers(last_user[sid], text)
                if miss:
                    for conn, rl in rooms.get(sid, []):
                        if rl == "translator": await conn.send_json({"type": "assist", "msg": f"Check numbers possibly omitted: {miss}"})
    except Exception: pass
    finally:
        rooms[sid] = [x for x in rooms.get(sid, []) if x[0] is not websocket]; db.close()
