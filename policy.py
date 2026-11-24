"""Jurisdiction-aware policy engine. Rules are code-reviewed data: change them here, with counsel, and log the version."""
from datetime import datetime, timedelta
from .config import settings
from .models import Credential, TranslatorProfile, Job, SessionLine
POLICY_VERSION = "2026-01"
REQUIRED = {"Medical": {"CCHI", "NBCMI"}, "Legal": {"COURT"}, "Immigration": {"CERT_TRANSLATOR", "ATA"}}
DOMAINS = ["General", "Business", "Immigration", "Medical", "Legal"]
def evaluate(domain, country):
    sensitive = domain in ("Medical", "Legal")
    return {
        "version": POLICY_VERSION,
        "human_required": True,                       # AI output is never delivered without human approval
        "ai_assist_only": sensitive,
        "credential_any_of": sorted(REQUIRED.get(domain, [])),
        "all_party_consent": country == "US",         # US recording laws vary by state: be conservative
        "recording_default": False,
        "consents_required": ["transcription", "ai_processing"],
        "vn_cross_border_tracking": country == "VN",  # Vietnam PDPL: transfer impact assessment to be filed
        "ai_vendor_needs_baa": domain == "Medical" and country == "US",
        "ai_disclosure": "AI-generated content. A qualified human interpreter or translator remains responsible.",
    }
def ai_allowed(domain, country):
    """Block sending sensitive data to an AI vendor until a BAA / zero-retention agreement is declared."""
    if evaluate(domain, country)["ai_vendor_needs_baa"] and not settings.AI_VENDOR_BAA: return False
    return True
def translator_ok(db, user, pair_id, domain):
    if user.role != "translator" or user.status != "active": return False
    p = db.get(TranslatorProfile, user.id)
    if not p or pair_id not in p.pairs or domain not in p.domains: return False
    need = REQUIRED.get(domain)
    if not need: return True
    return db.query(Credential).filter(Credential.user_id == user.id, Credential.type.in_(need),
        Credential.verified == True, Credential.expires_at > datetime.utcnow()).first() is not None  # noqa: E712
def purge(db):
    """Retention: delete old transcripts and blank old delivered source text. Run on a schedule (cron)."""
    t1 = datetime.utcnow() - timedelta(days=settings.TRANSCRIPT_RETENTION_DAYS)
    n1 = db.query(SessionLine).filter(SessionLine.ts < t1).delete()
    t2 = datetime.utcnow() - timedelta(days=settings.SOURCE_RETENTION_DAYS)
    jobs = db.query(Job).filter(Job.status == "DELIVERED", Job.approved_at < t2, Job.source_text != "").all()
    for j in jobs: j.source_text = ""; j.final_text = ""
    db.commit(); return {"transcript_lines_deleted": n1, "jobs_blanked": len(jobs)}
