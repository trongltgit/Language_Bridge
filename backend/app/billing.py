import hashlib
from math import ceil
from fastapi import HTTPException
from .config import settings
from .db import get_setting
from .models import Ledger
MULT = {"General": 1.0, "Business": 1.1, "Immigration": 1.2, "Medical": 1.25, "Legal": 1.4}
MIN_MINUTES = 15
def doc_price(pair, domain, words, rush): return round(words * pair.word_rate * MULT[domain] * (1.5 if rush else 1), 2)
def minute_rate(pair, domain): return round(pair.min_rate * MULT[domain], 4)
def minutes_billed(seconds, started=True): return max(MIN_MINUTES, ceil(max(seconds, 0) / 60)) if started else 0   # nothing billed if never all connected
def post(db, type_, ref, amount, account="platform"):
    db.add(Ledger(type=type_, ref=str(ref), account=account, amount=round(amount, 2))); db.commit()
def settle(db, ref, gross, translator_public_id):
    pct = get_setting(db, "commission_pct", settings.COMMISSION_PCT)
    fee = round(gross * pct / 100, 2)
    post(db, "COMMISSION", ref, fee, "platform"); post(db, "PAYOUT_PENDING", ref, gross - fee, translator_public_id)
    return fee, round(gross - fee, 2)
def charge(user, amount, ref):
    """INTEGRATION POINT. 'simulated' always succeeds. Replace with Stripe (US) / VNPay, MoMo (VN) PaymentIntents,
    verify webhooks, and hold funds until approval (escrow-style)."""
    if settings.PAYMENTS_MODE == "simulated": return "SIM-" + hashlib.sha1(f"{user.id}{ref}".encode()).hexdigest()[:10]
    raise HTTPException(501, "Payment gateway not configured")
