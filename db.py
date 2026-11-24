from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import settings
kw = {"connect_args": {"check_same_thread": False}} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, **kw)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
def audit(db, actor, action, detail=""):
    from .models import Audit
    db.add(Audit(ts=datetime.utcnow(), actor=actor, action=action, detail=detail[:2000])); db.commit()
def get_setting(db, key, default):
    from .models import Setting
    s = db.get(Setting, key)
    return type(default)(s.value) if s else default
def set_setting(db, key, value):
    from .models import Setting
    s = db.get(Setting, key)
    if s: s.value = str(value)
    else: db.add(Setting(key=key, value=str(value)))
    db.commit()
