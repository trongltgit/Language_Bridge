import os
def _b(k, d="false"): return os.getenv(k, d).lower() == "true"
class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lingua.db").replace("postgres://", "postgresql://", 1)
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
    JWT_MINUTES = int(os.getenv("JWT_MINUTES", "60"))
    REQUIRE_MFA = _b("REQUIRE_MFA")                 # admin + translator MFA enforcement
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "claude-sonnet-5-5")
    AI_VENDOR_BAA = _b("AI_VENDOR_BAA")             # set true ONLY after a signed BAA / zero-retention terms
    PAYMENTS_MODE = os.getenv("PAYMENTS_MODE", "simulated")
    COMMISSION_PCT = float(os.getenv("COMMISSION_PCT", "20"))
    MEMBERSHIP_USD = float(os.getenv("MEMBERSHIP_USD", "15"))
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")  # >=12 chars, creates first admin on startup
    LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
    LIVEKIT_KEY = os.getenv("LIVEKIT_API_KEY", "")
    LIVEKIT_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
    TRANSCRIPT_RETENTION_DAYS = int(os.getenv("TRANSCRIPT_RETENTION_DAYS", "30"))
    SOURCE_RETENTION_DAYS = int(os.getenv("SOURCE_RETENTION_DAYS", "30"))
settings = Settings()
