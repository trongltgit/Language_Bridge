from fastapi import APIRouter, Depends
from ..db import get_db
from ..models import LanguagePair
from .. import policy, billing
from .billing_api import PLANS
r = APIRouter(tags=["public"])
@r.get("/pairs")
def pairs(db=Depends(get_db)):
    return [{"id": p.id, "name": p.name, "word_rate": p.word_rate, "min_rate": p.min_rate, "status": p.status} for p in db.query(LanguagePair)]
@r.get("/meta")
def meta():
    return {"domains": policy.DOMAINS, "plans": PLANS, "multipliers": billing.MULT, "min_minutes": billing.MIN_MINUTES, "usd_vnd": 25000, "policy_version": policy.POLICY_VERSION}
@r.get("/policy/{domain}/{country}")
def show(domain: str, country: str): return policy.evaluate(domain, country.upper())
