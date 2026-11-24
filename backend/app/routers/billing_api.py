from fastapi import APIRouter, Depends, HTTPException
from ..db import get_db, audit
from ..models import Subscription, User
from ..security import require
from .. import billing
r = APIRouter(prefix="/billing", tags=["billing"])
PLANS = {"Basic": 9, "Pro": 29, "Business": 99}
@r.get("/plans")
def plans(): return PLANS
@r.post("/subscribe")
def subscribe(plan: str, u: User = Depends(require("user")), db=Depends(get_db)):
    if plan not in PLANS: raise HTTPException(422, "Unknown plan")
    if db.query(Subscription).filter(Subscription.user_id == u.id, Subscription.status == "active").first(): raise HTTPException(409, "Already subscribed")
    ref = billing.charge(u, PLANS[plan], "sub-" + plan); db.add(Subscription(user_id=u.id, plan=plan, price=PLANS[plan])); db.commit()
    billing.post(db, "SUBSCRIPTION", plan, PLANS[plan], u.public_id); audit(db, u.public_id, "subscribed", plan); return {"plan": plan, "ref": ref}
@r.post("/cancel")
def cancel(u: User = Depends(require("user")), db=Depends(get_db)):
    s = db.query(Subscription).filter(Subscription.user_id == u.id, Subscription.status == "active").first()
    if not s: raise HTTPException(404, "No active subscription")
    s.status = "cancelled"; db.commit(); audit(db, u.public_id, "sub_cancelled"); return {"status": "cancelled"}
@r.get("/me")
def my_sub(u: User = Depends(require("user")), db=Depends(get_db)):
    s = db.query(Subscription).filter(Subscription.user_id == u.id, Subscription.status == "active").first()
    return {"plan": s.plan, "price": s.price} if s else {"plan": None}
