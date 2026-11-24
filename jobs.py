import io, re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from ..db import get_db, audit, get_setting
from ..models import Job, JobVersion, LanguagePair, Subscription, User, Ledger, Consent
from ..security import require, current_user
from .. import ai, billing, policy
r = APIRouter(tags=["documents"])
NEXT = {"CREATED": {"PAID"}, "PAID": {"AI_DRAFTED"}, "AI_DRAFTED": {"IN_REVIEW"}, "IN_REVIEW": {"APPROVED"},
        "APPROVED": {"DELIVERED", "IN_REVIEW"}, "DELIVERED": {"IN_REVIEW"}}
def move(db, j, new):
    if new not in NEXT.get(j.status, set()): raise HTTPException(409, f"Illegal status change {j.status} -> {new}")
    j.status = new; db.commit()
CJK = r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]"
def count_words(t): return len(re.findall(CJK, t)) + len(re.sub(CJK, " ", t).split())
def extract_text(name, data):
    n = name.lower()
    if n.endswith((".txt", ".md")): return data.decode("utf-8", "ignore")
    if n.endswith(".docx"):
        import docx; return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
    if n.endswith(".pdf"):
        from pypdf import PdfReader; return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    raise HTTPException(415, "Unsupported file. Scans and images need an OCR service (integration point).")
def _job(db, jid):
    j = db.get(Job, jid)
    if not j: raise HTTPException(404, "No such job")
    return j
def _mine_tr(db, u, jid):
    j = _job(db, jid)
    if j.translator_id != u.id: raise HTTPException(403, "Not your assignment")
    return j
def _pair(db, pid, need_live=True):
    p = db.get(LanguagePair, pid)
    if not p or (need_live and p.status != "LIVE"): raise HTTPException(422, "Language pair not available")
    return p
def active_sub(db, u):
    if not db.query(Subscription).filter(Subscription.user_id == u.id, Subscription.status == "active").first():
        raise HTTPException(402, "An active subscription is required")
@r.post("/jobs")
async def create(pair_id: str = Form(...), domain: str = Form(...), rush: bool = Form(False), file: UploadFile = File(...),
                 u: User = Depends(require("user")), db=Depends(get_db)):
    active_sub(db, u)
    if domain not in billing.MULT: raise HTTPException(422, f"domain must be one of {list(billing.MULT)}")
    p = _pair(db, pair_id); data = await file.read()
    if len(data) > 10_000_000: raise HTTPException(413, "File too large (10 MB max)")
    text = extract_text(file.filename or "file", data)
    if not text.strip(): raise HTTPException(422, "No text found. Scanned files need OCR.")
    w = count_words(text); price = billing.doc_price(p, domain, w, rush)
    j = Job(user_id=u.id, pair_id=pair_id, domain=domain, filename=file.filename, source_text=text, words=w, price=price, rush=rush)
    db.add(j); db.commit(); audit(db, u.public_id, "job_created", f"{j.id} {domain} {w}w")
    return {"id": j.id, "words": w, "quote_usd": price, "policy": policy.evaluate(domain, u.region)}
@r.post("/jobs/{jid}/pay")
def pay(jid: int, u: User = Depends(require("user")), db=Depends(get_db)):
    j = _job(db, jid)
    if j.user_id != u.id: raise HTTPException(403, "Not your job")
    ref = billing.charge(u, j.price, j.id); billing.post(db, "USER_CHARGE", j.id, j.price, u.public_id); move(db, j, "PAID")
    p = db.get(LanguagePair, j.pair_id); src, tgt = j.pair_id.split("-")
    if policy.ai_allowed(j.domain, u.region): d = ai.draft(j.source_text, src, tgt, j.domain)
    else: d = f"{ai.MARK}\n{j.source_text}"; audit(db, "system", "ai_blocked_by_policy", f"job {j.id}")
    db.add(JobVersion(job_id=j.id, kind="AI_DRAFT", content=d, by="ai")); j.final_text = d; db.commit()
    move(db, j, "AI_DRAFTED"); audit(db, u.public_id, "job_paid", f"{j.id} {ref}")
    return {"id": j.id, "status": j.status}
@r.get("/jobs")
def listing(u: User = Depends(current_user), db=Depends(get_db)):
    q = db.query(Job)
    if u.role == "user": q = q.filter(Job.user_id == u.id)
    elif u.role == "translator":
        prof = [j for j in q.filter(Job.status == "AI_DRAFTED") if policy.translator_ok(db, u, j.pair_id, j.domain)]
        own = q.filter(Job.translator_id == u.id).all()
        rows = {j.id: j for j in prof + own}.values()
        pct = get_setting(db, "commission_pct", 20.0)
        return [{"id": j.id, "pair": j.pair_id, "domain": j.domain, "words": j.words, "status": j.status, "value": j.price,
                 "fee": round(j.price * pct / 100, 2), "you_earn": round(j.price * (100 - pct) / 100, 2)} for j in rows]
    # users and admins see metadata only, never content (admin needs break-glass)
    return [{"id": j.id, "file": j.filename, "pair": j.pair_id, "domain": j.domain, "status": j.status if j.status in ("APPROVED", "DELIVERED") else ("IN_REVIEW" if j.status != "CREATED" else "CREATED"), "price": j.price} for j in q]
@r.post("/jobs/{jid}/accept")
def accept(jid: int, u: User = Depends(require("translator")), db=Depends(get_db)):
    j = _job(db, jid)
    if j.status != "AI_DRAFTED" or j.translator_id: raise HTTPException(409, "Job is not available")
    if not policy.translator_ok(db, u, j.pair_id, j.domain): raise HTTPException(403, "Missing language pair, domain or verified credential")
    j.translator_id = u.id; move(db, j, "IN_REVIEW"); audit(db, u.public_id, "job_accepted", str(jid))
    return {"source": j.source_text, "ai_draft": j.final_text, "policy": policy.evaluate(j.domain, "US")}
@r.get("/jobs/{jid}/work")
def work(jid: int, u: User = Depends(require("translator")), db=Depends(get_db)):
    j = _mine_tr(db, u, jid)
    return {"id": j.id, "status": j.status, "pair": j.pair_id, "domain": j.domain, "source": j.source_text, "draft": j.final_text, "qa": j.qa, "policy": policy.evaluate(j.domain, "US")}
class Draft(BaseModel): text: str
@r.put("/jobs/{jid}/draft")
def save(jid: int, b: Draft, u: User = Depends(require("translator")), db=Depends(get_db)):
    j = _mine_tr(db, u, jid)
    if j.status != "IN_REVIEW": raise HTTPException(409, "Job is not in review")
    j.final_text = b.text; j.qa = None; db.add(JobVersion(job_id=j.id, kind="TRANSLATOR_EDIT", content=b.text, by=u.public_id)); db.commit()
    return {"saved": True, "qa_required": True}
@r.post("/jobs/{jid}/qa")
def run_qa(jid: int, u: User = Depends(require("translator")), db=Depends(get_db)):
    j = _mine_tr(db, u, jid); j.qa = ai.qa(j.source_text, j.final_text); db.commit()
    return {"flags": j.qa, "note": "Proposals only. Your text is never changed automatically."}
@r.post("/jobs/{jid}/approve")
def approve(jid: int, u: User = Depends(require("translator")), db=Depends(get_db)):
    j = _mine_tr(db, u, jid)
    if j.qa is None: raise HTTPException(409, "Run QA after your last edit before approving")
    if ai.MARK in j.final_text: raise HTTPException(409, "AI placeholder still in text")
    j.approved_at = datetime.utcnow(); src, tgt = j.pair_id.split("-")
    if j.domain == "Immigration":
        j.certificate = (f"Certification: I, {u.name} (ID {u.public_id}), certify that I am competent to translate from {src} into {tgt} "
                         f"and that this is a complete and accurate translation of the document. Date: {j.approved_at:%Y-%m-%d}. Signature: ________")
    db.add(JobVersion(job_id=j.id, kind="FINAL", content=j.final_text, by=u.public_id)); move(db, j, "APPROVED")
    fee, net = billing.settle(db, j.id, j.price, u.public_id); audit(db, u.public_id, "job_approved", f"{jid} fee {fee} net {net}")
    return {"status": "APPROVED", "fee": fee, "you_earn": net}
@r.get("/jobs/{jid}/result")
def result(jid: int, u: User = Depends(require("user")), db=Depends(get_db)):
    j = _job(db, jid)
    if j.user_id != u.id: raise HTTPException(403, "Not your job")
    if j.status not in ("APPROVED", "DELIVERED"): raise HTTPException(409, "Not available until the translator approves")
    if j.status == "APPROVED": move(db, j, "DELIVERED")
    return {"text": j.final_text, "certificate": j.certificate, "notice": policy.evaluate(j.domain, u.region)["ai_disclosure"]}
@r.post("/jobs/{jid}/revision")
def revision(jid: int, u: User = Depends(require("user")), db=Depends(get_db)):
    j = _job(db, jid)
    if j.user_id != u.id: raise HTTPException(403, "Not your job")
    if not j.approved_at or datetime.utcnow() - j.approved_at > timedelta(days=7): raise HTTPException(409, "Revision window (7 days) has passed")
    move(db, j, "IN_REVIEW"); j.qa = None; db.commit(); audit(db, u.public_id, "revision_requested", str(jid)); return {"status": j.status}
@r.get("/translator/earnings")
def earnings(u: User = Depends(require("translator")), db=Depends(get_db)):
    rows = db.query(Ledger).filter(Ledger.type == "PAYOUT_PENDING", Ledger.account == u.public_id).all()
    return {"net_pending": round(sum(x.amount for x in rows), 2), "items": [{"ref": x.ref, "amount": x.amount} for x in rows],
            "membership_usd": get_setting(db, "membership_usd", 15.0), "note": "Membership is net-settled from earnings."}
