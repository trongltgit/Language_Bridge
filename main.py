import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .config import settings
from .db import engine, SessionLocal
from .models import Base, LanguagePair, User
from .security import hash_pw
from .routers import auth, admin, jobs, interpreting, billing_api, public
def boot():
    if not settings.DATABASE_URL.startswith("sqlite") and (settings.JWT_SECRET.startswith("dev-only") or len(settings.JWT_SECRET) < 32):
        raise RuntimeError("Set JWT_SECRET to a random string of 32+ characters before using a real database")
    Base.metadata.create_all(engine)   # test deployments only. Production: use Alembic migrations (see docs/PRODUCTION.md)
    db = SessionLocal()
    if not db.query(LanguagePair).count():
        db.add_all([LanguagePair(id="vi-en", name="Vietnamese-English", word_rate=.12, min_rate=1.2, status="LIVE"),
                    LanguagePair(id="es-en", name="Spanish-English", word_rate=.10, min_rate=1.0, status="LIVE"),
                    LanguagePair(id="zh-en", name="Chinese-English", word_rate=.11, min_rate=1.1, status="BETA"),
                    LanguagePair(id="ko-en", name="Korean-English", word_rate=.12, min_rate=1.2, status="PLANNED")])
    if len(settings.ADMIN_PASSWORD) >= 12 and not db.query(User).filter(User.role == "admin").first():
        db.add(User(public_id="AD-0001", email=settings.ADMIN_EMAIL.lower(), name="Platform Admin", role="admin", status="active", pw_hash=hash_pw(settings.ADMIN_PASSWORD)))
    db.commit(); db.close()
@asynccontextmanager
async def lifespan(app):
    boot(); yield
app = FastAPI(title="LinguaBridge API", version="0.2.0", lifespan=lifespan)
CSP = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'"
@app.middleware("http")
async def headers(request, call_next):
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                         "Strict-Transport-Security": "max-age=31536000; includeSubDomains", "Permissions-Policy": "microphone=(self), camera=(self)"})
    if not request.url.path.startswith(("/docs", "/openapi", "/redoc")): resp.headers["Content-Security-Policy"] = CSP
    if request.url.path.startswith(("/auth", "/admin", "/jobs", "/sessions", "/billing", "/translator")): resp.headers["Cache-Control"] = "no-store"
    return resp
for m in (auth, admin, jobs, interpreting, billing_api, public): app.include_router(m.r)
@app.get("/health")
def health(): return {"ok": True}
for d in (os.getenv("FRONTEND_DIR"), "/srv/frontend", str(Path(__file__).resolve().parents[2] / "frontend")):
    if d and os.path.isdir(d): app.mount("/", StaticFiles(directory=d, html=True), name="ui"); break
