from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
class Base(DeclarativeBase): pass
_now = datetime.utcnow
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(12), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(12))            # admin | user | translator
    status: Mapped[str] = mapped_column(String(12), default="invited")  # invited | active | suspended | erased
    pw_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    invite_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    region: Mapped[str] = mapped_column(String(4), default="US")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
class TranslatorProfile(Base):
    __tablename__ = "translator_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    pairs: Mapped[list] = mapped_column(JSON, default=list)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(20))            # CCHI NBCMI COURT CERT_TRANSLATOR ATA
    number: Mapped[str] = mapped_column(String(60))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
class LanguagePair(Base):
    __tablename__ = "language_pairs"
    id: Mapped[str] = mapped_column(String(10), primary_key=True)   # e.g. vi-en
    name: Mapped[str] = mapped_column(String(60))
    word_rate: Mapped[float] = mapped_column(Float)
    min_rate: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="LIVE")  # LIVE BETA PLANNED PAUSED
class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan: Mapped[str] = mapped_column(String(20)); price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    translator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    pair_id: Mapped[str] = mapped_column(ForeignKey("language_pairs.id"))
    domain: Mapped[str] = mapped_column(String(15)); filename: Mapped[str] = mapped_column(String(255))
    source_text: Mapped[str] = mapped_column(Text, default=""); final_text: Mapped[str] = mapped_column(Text, default="")
    words: Mapped[int] = mapped_column(Integer); price: Mapped[float] = mapped_column(Float); rush: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="CREATED")
    qa: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)   # None = QA not run since last edit
    certificate: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
class JobVersion(Base):
    __tablename__ = "job_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    kind: Mapped[str] = mapped_column(String(20))            # AI_DRAFT TRANSLATOR_EDIT FINAL
    content: Mapped[str] = mapped_column(Text); by: Mapped[str] = mapped_column(String(40))
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now)
class InterpSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    translator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    pair_id: Mapped[str] = mapped_column(ForeignKey("language_pairs.id"))
    domain: Mapped[str] = mapped_column(String(15)); country: Mapped[str] = mapped_column(String(4))
    guest_token: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(10), default="OPEN")   # OPEN ENDED
    joined: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    minutes_billed: Mapped[int] = mapped_column(Integer, default=0)
class SessionLine(Base):
    __tablename__ = "session_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    speaker: Mapped[str] = mapped_column(String(12)); texts: Mapped[dict] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now)
class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    who: Mapped[str] = mapped_column(String(40)); ref: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(30)); version: Mapped[str] = mapped_column(String(10), default="2026-01")
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now)
class Ledger(Base):
    __tablename__ = "ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now)
    type: Mapped[str] = mapped_column(String(20))   # SUBSCRIPTION USER_CHARGE COMMISSION PAYOUT_PENDING REFUND CLAWBACK
    ref: Mapped[str] = mapped_column(String(30)); account: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Float); currency: Mapped[str] = mapped_column(String(3), default="USD")
class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now)
    actor: Mapped[str] = mapped_column(String(40)); action: Mapped[str] = mapped_column(String(60)); detail: Mapped[str] = mapped_column(Text, default="")
class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True); value: Mapped[str] = mapped_column(String(100))
