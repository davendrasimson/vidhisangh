"""Seed realistic **sample** tenant data (matters, CRM leads, knowledge base,
invoices) + global marketplace listings — NOT real data. For testing / design.

Targets one tenant (default: the tenant of ds@simsononline.com). Every batch is
marked so it can be cleared and re-seeded without touching real records:
  matters    → matter_number  starts 'SMP/'
  invoices   → invoice_number starts 'SMP-INV/'
  leads      → email ends '@sample.vidhisangh.local'
  knowledge  → carries a 'sample' tag
  listings   → description ends '[sample-data]'

Run:  python -m app.scripts.seed_sample_tenant --count 5000
      python -m app.scripts.seed_sample_tenant --clear
      python -m app.scripts.seed_sample_tenant --email priya@sharma-legal.co
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import structlog
from faker import Faker
from sqlalchemy import Text, delete, insert, select

import app.db.base  # noqa: F401
from app.core.database import session_scope
from app.modules.billing.models import Invoice, InvoiceLineItem, InvoiceStatus
from app.modules.calendar.models import CalendarEvent, EventType
from app.modules.crm.models import ActivityType, Lead, LeadActivity, LeadSource, LeadStatus
from app.modules.documents.models import Document, DocumentFolder, DocumentVersion
from app.modules.identity.models import User
from app.modules.knowledge.models import KnowledgeCategory, KnowledgeItem
from app.modules.marketplace.models import Listing, ListingStatus, ListingType
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.matters.models import (
    Hearing,
    HearingStatus,
    Matter,
    MatterNote,
    MatterParty,
    MatterStage,
    MatterStatus,
    MatterTask,
    MatterType,
    Priority,
    TaskStatus,
)

log = structlog.get_logger("app.seed_sample_tenant")
fake = Faker("en_IN")
Faker.seed(7)
rnd = fake.random

PRACTICE_AREAS = [
    "Civil Litigation", "Criminal Defence", "Corporate & M&A", "Taxation", "Arbitration",
    "Real Estate", "Family Law", "Intellectual Property", "Banking & Finance",
    "Employment & Labour", "Constitutional Law", "Insolvency", "Consumer Protection",
    "Environmental Law",
]
COURTS = [
    "Supreme Court of India", "Delhi High Court", "Bombay High Court", "NCLT Mumbai",
    "District Court, Saket", "Karnataka High Court", "ITAT Delhi", "DRT Chennai",
]
LISTING_LOCATIONS = ["Delhi", "Mumbai", "Bengaluru", "Chennai", "Kolkata", "Pune", "Hyderabad", "Remote"]


def _money(a: int, b: int) -> Decimal:
    return Decimal(rnd.randint(a, b))


def _day(back: int, fwd: int = 0) -> date:
    return (datetime.now(timezone.utc) + timedelta(days=rnd.randint(-back, fwd))).date()


def _dt(back: int, fwd: int) -> datetime:
    return (datetime.now(timezone.utc) + timedelta(days=rnd.randint(-back, fwd))).replace(tzinfo=None)


# ─── Matters (+ parties, hearings, tasks, notes) ─────────────────────
def _matter_rows(count: int, tid: uuid.UUID, uid: uuid.UUID):
    matters, parties, hearings, tasks, notes = [], [], [], [], []
    for i in range(count):
        mid = uuid.uuid4()
        year = rnd.randint(2021, 2025)
        client = fake.name() if rnd.random() < 0.6 else fake.company()
        opponent = fake.company() if rnd.random() < 0.5 else fake.name()
        mtype = rnd.choice(list(MatterType))
        status = rnd.choices(list(MatterStatus), weights=[65, 15, 20])[0]
        matters.append({
            "id": mid, "tenant_id": tid,
            "matter_number": f"SMP/{year}/{i + 1:05d}",
            "title": f"{client} — {rnd.choice(PRACTICE_AREAS)} matter",
            "client_name": client,
            "matter_type": mtype.value,
            "status": status.value,
            "stage": rnd.choice(list(MatterStage)).value,
            "priority": rnd.choices(list(Priority), weights=[40, 45, 15])[0].value,
            "practice_area": rnd.choice(PRACTICE_AREAS),
            "court": rnd.choice(COURTS),
            "case_number": f"CS/{rnd.randint(100, 9999)}/{year}",
            "description": fake.paragraph(nb_sentences=2),
            "opened_on": _day(1400),
            "limitation_date": _day(-30, 400) if rnd.random() < 0.5 else None,
            "assigned_to": uid, "created_by": uid,
        })
        for role, nm in (("Petitioner", client), ("Respondent", opponent)):
            parties.append({"id": uuid.uuid4(), "tenant_id": tid, "matter_id": mid,
                            "name": nm, "role": role, "contact": fake.phone_number()})
        if rnd.random() < 0.45:
            hearings.append({"id": uuid.uuid4(), "tenant_id": tid, "matter_id": mid,
                             "scheduled_on": _dt(120, 120), "court": rnd.choice(COURTS),
                             "judge": f"Hon'ble Justice {fake.last_name()}",
                             "purpose": rnd.choice(["Arguments", "Evidence", "Framing of issues", "Final hearing"]),
                             "status": rnd.choice(list(HearingStatus)).value, "notes": None, "outcome": None,
                             "next_date": None})
        for _ in range(rnd.randint(0, 3)):
            done = rnd.random() < 0.4
            tasks.append({"id": uuid.uuid4(), "tenant_id": tid, "matter_id": mid,
                          "title": rnd.choice(["Draft reply", "File vakalatnama", "Prepare brief",
                                               "Serve notice", "Review documents", "Client update"]),
                          "due_on": _day(30, 60), "status": (TaskStatus.DONE if done else TaskStatus.OPEN).value,
                          "assigned_to": uid, "completed_at": _dt(30, 0) if done else None})
        if rnd.random() < 0.3:
            notes.append({"id": uuid.uuid4(), "tenant_id": tid, "matter_id": mid,
                          "author_id": uid, "body": fake.paragraph(nb_sentences=2)})
    return matters, parties, hearings, tasks, notes


# ─── Leads (+ activities) ────────────────────────────────────────────
def _lead_rows(count: int, tid: uuid.UUID, uid: uuid.UUID):
    leads, acts = [], []
    for i in range(count):
        lid = uuid.uuid4()
        nm = fake.name()
        leads.append({
            "id": lid, "tenant_id": tid, "name": nm,
            "email": f"{nm.lower().replace(' ', '.').replace(chr(46) + chr(46), chr(46))}.{i}@sample.vidhisangh.local",
            "phone": fake.phone_number(),
            "source": rnd.choice(list(LeadSource)).value,
            "status": rnd.choices(list(LeadStatus), weights=[30, 20, 15, 12, 13, 10])[0].value,
            "practice_area": rnd.choice(PRACTICE_AREAS),
            "notes": fake.sentence(),
            "estimated_value": _money(25000, 2000000),
            "referred_by": fake.name() if rnd.random() < 0.4 else None,
            "assigned_to": uid, "converted_matter_id": None, "created_by": uid,
        })
        for _ in range(rnd.randint(0, 2)):
            acts.append({"id": uuid.uuid4(), "tenant_id": tid, "lead_id": lid,
                         "type": rnd.choice(list(ActivityType)).value,
                         "subject": rnd.choice(["Intro call", "Sent proposal", "Follow-up", "Consultation booked"]),
                         "body": fake.sentence(), "due_on": _day(0, 30),
                         "completed": rnd.random() < 0.5, "completed_at": None, "created_by": uid})
    return leads, acts


def _knowledge_rows(count: int, tid: uuid.UUID, uid: uuid.UUID):
    kinds = {
        KnowledgeCategory.TEMPLATE: "Template", KnowledgeCategory.PRECEDENT: "Precedent",
        KnowledgeCategory.SOP: "SOP", KnowledgeCategory.CHECKLIST: "Checklist",
        KnowledgeCategory.NOTE: "Note",
    }
    rows = []
    for _ in range(count):
        cat = rnd.choice(list(KnowledgeCategory))
        pa = rnd.choice(PRACTICE_AREAS)
        rows.append({"id": uuid.uuid4(), "tenant_id": tid,
                     "title": f"{kinds[cat]}: {pa} — {fake.bs().title()}",
                     "category": cat.value, "body": fake.paragraph(nb_sentences=5),
                     "practice_area": pa, "tags": ["sample", pa.lower().split()[0], cat.value],
                     "created_by": uid})
    return rows


def _listing_rows(count: int, tid: uuid.UUID, uid: uuid.UUID, poster: str):
    rows = []
    for _ in range(count):
        lt = rnd.choice(list(ListingType))
        pa = rnd.choice(PRACTICE_AREAS)
        rows.append({"id": uuid.uuid4(), "type": lt.value,
                     "title": f"{lt.value.replace('_', ' ').title()} needed — {pa}",
                     "description": f"{fake.paragraph(nb_sentences=3)} [sample-data]",
                     "practice_area": pa, "location": rnd.choice(LISTING_LOCATIONS),
                     "budget": _money(5000, 500000) if rnd.random() < 0.7 else None,
                     "status": rnd.choices(list(ListingStatus), weights=[80, 20])[0].value,
                     "posted_by": uid, "poster_name": poster, "poster_tenant_id": tid,
                     "response_count": rnd.randint(0, 8)})
    return rows


def _invoice_rows(count: int, tid: uuid.UUID, uid: uuid.UUID):
    invoices, items = [], []
    for i in range(count):
        iid = uuid.uuid4()
        year = rnd.randint(2023, 2025)
        status = rnd.choices(list(InvoiceStatus), weights=[15, 25, 40, 15, 5])[0]
        n_items = rnd.randint(1, 3)
        subtotal = Decimal(0)
        for _ in range(n_items):
            qty = Decimal(rnd.randint(1, 10))
            price = _money(2000, 60000)
            amount = qty * price
            subtotal += amount
            items.append({"id": uuid.uuid4(), "tenant_id": tid, "invoice_id": iid,
                          "description": rnd.choice(["Professional fees", "Court appearance",
                                                     "Drafting charges", "Consultation", "Research"]),
                          "quantity": qty, "unit_price": price, "amount": amount})
        rate = Decimal(18)
        tax = (subtotal * rate / 100).quantize(Decimal("1.00"))
        total = subtotal + tax
        paid = total if status == InvoiceStatus.PAID else (
            (total / 2).quantize(Decimal("1.00")) if rnd.random() < 0.2 else Decimal(0))
        invoices.append({"id": iid, "tenant_id": tid,
                         "invoice_number": f"SMP-INV/{year}/{i + 1:05d}",
                         "client_name": fake.name() if rnd.random() < 0.6 else fake.company(),
                         "matter_id": None, "status": status.value,
                         "issue_date": _day(700), "due_date": _day(100, 60),
                         "currency": "INR", "tax_rate": rate, "subtotal": subtotal,
                         "tax_amount": tax, "total": total, "amount_paid": paid,
                         "notes": None, "created_by": uid})
    return invoices, items


# ─── Calendar events ─────────────────────────────────────────────────
def _event_rows(count: int, tid: uuid.UUID, uid: uuid.UUID):
    rows = []
    for _ in range(count):
        start = _dt(90, 120)
        et = rnd.choice(list(EventType))
        rows.append({"id": uuid.uuid4(), "tenant_id": tid,
                     "title": f"{et.value.title()}: {fake.catch_phrase()}",
                     "description": f"{fake.sentence()} [sample-data]",
                     "event_type": et.value, "start_at": start,
                     "end_at": start + timedelta(hours=rnd.randint(1, 3)),
                     "all_day": rnd.random() < 0.15, "location": rnd.choice(COURTS + LISTING_LOCATIONS),
                     "matter_id": None, "assigned_to": uid, "created_by": uid})
    return rows


# ─── Documents (+ folders, one version each) ─────────────────────────
def _document_rows(count: int, tid: uuid.UUID, uid: uuid.UUID):
    folders = [{"id": uuid.uuid4(), "tenant_id": tid,
                "name": f"Sample: {rnd.choice(PRACTICE_AREAS)} — {fake.word().title()}",
                "parent_id": None, "matter_id": None, "created_by": uid}
               for _ in range(max(1, count // 25))]
    fids = [f["id"] for f in folders]
    ctypes = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "image/jpeg", "text/plain", "application/vnd.ms-excel"]
    exts = {"application/pdf": "pdf", "image/jpeg": "jpg", "text/plain": "txt",
            "application/vnd.ms-excel": "xls",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}
    docs, versions = [], []
    for _ in range(count):
        did, vid = uuid.uuid4(), uuid.uuid4()
        ct = rnd.choice(ctypes)
        size = rnd.randint(20_000, 8_000_000)
        docs.append({"id": did, "tenant_id": tid,
                     "name": f"{fake.word().title()}_{rnd.choice(['Petition', 'Affidavit', 'Contract', 'Notice', 'Order'])}.{exts[ct]}",
                     "folder_id": rnd.choice(fids), "matter_id": None, "content_type": ct, "size": size,
                     "tags": ["sample", rnd.choice(PRACTICE_AREAS).lower().split()[0]],
                     "current_version_id": vid, "version_count": 1,
                     "locked_by": None, "locked_at": None, "uploaded_by": uid})
        versions.append({"id": vid, "tenant_id": tid, "document_id": did, "version_no": 1,
                         "storage_key": f"sample/{did}", "size": size, "content_type": ct,
                         "checksum": (uuid.uuid4().hex + uuid.uuid4().hex), "comment": "Initial upload",
                         "uploaded_by": uid})
    return folders, docs, versions


# ─── Payments ────────────────────────────────────────────────────────
def _payment_rows(count: int, tid: uuid.UUID, uid: uuid.UUID, invoice_ids: list):
    rows = []
    for i in range(count):
        status = rnd.choices(list(PaymentStatus), weights=[15, 70, 10, 5])[0]
        paid = status in (PaymentStatus.PAID, PaymentStatus.REFUNDED)
        inv = rnd.choice(invoice_ids) if invoice_ids and rnd.random() < 0.6 else None
        rows.append({"id": uuid.uuid4(), "tenant_id": tid,
                     "amount": rnd.randint(50000, 50000000),  # paise
                     "currency": "INR", "status": status.value, "provider": "mock",
                     "provider_order_id": f"order_SMP{i + 1:06d}",
                     "provider_payment_id": f"pay_SMP{i + 1:06d}" if paid else None,
                     "receipt": f"rcpt_SMP{i + 1:06d}", "description": "Fee payment",
                     "matter_id": None, "invoice_id": inv, "created_by": uid,
                     "paid_at": _dt(200, 0) if paid else None})
    return rows


async def _clear(session, tid: uuid.UUID) -> None:
    m_ids = (await session.execute(
        select(Matter.id).where(Matter.tenant_id == tid, Matter.matter_number.like("SMP/%"))
    )).scalars().all()
    for model in (MatterParty, Hearing, MatterTask, MatterNote):
        if m_ids:
            await session.execute(delete(model).where(model.matter_id.in_(m_ids)))
    await session.execute(delete(Matter).where(Matter.matter_number.like("SMP/%"), Matter.tenant_id == tid))

    l_ids = (await session.execute(
        select(Lead.id).where(Lead.tenant_id == tid, Lead.email.like("%@sample.vidhisangh.local"))
    )).scalars().all()
    if l_ids:
        await session.execute(delete(LeadActivity).where(LeadActivity.lead_id.in_(l_ids)))
    await session.execute(delete(Lead).where(Lead.email.like("%@sample.vidhisangh.local"), Lead.tenant_id == tid))

    i_ids = (await session.execute(
        select(Invoice.id).where(Invoice.tenant_id == tid, Invoice.invoice_number.like("SMP-INV/%"))
    )).scalars().all()
    if i_ids:
        await session.execute(delete(InvoiceLineItem).where(InvoiceLineItem.invoice_id.in_(i_ids)))
    await session.execute(delete(Invoice).where(Invoice.invoice_number.like("SMP-INV/%"), Invoice.tenant_id == tid))

    await session.execute(
        delete(KnowledgeItem).where(KnowledgeItem.tenant_id == tid,
                                    KnowledgeItem.tags.cast(Text).like("%sample%"))
    )
    await session.execute(
        delete(Listing).where(Listing.poster_tenant_id == tid, Listing.description.like("%[sample-data]%"))
    )

    await session.execute(
        delete(CalendarEvent).where(CalendarEvent.tenant_id == tid,
                                    CalendarEvent.description.like("%[sample-data]%"))
    )
    await session.execute(delete(Payment).where(Payment.tenant_id == tid,
                                                Payment.provider_order_id.like("order_SMP%")))
    d_ids = (await session.execute(
        select(Document.id).where(Document.tenant_id == tid, Document.tags.cast(Text).like("%sample%"))
    )).scalars().all()
    if d_ids:
        await session.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(d_ids)))
    await session.execute(delete(Document).where(Document.tenant_id == tid,
                                                 Document.tags.cast(Text).like("%sample%")))
    await session.execute(delete(DocumentFolder).where(DocumentFolder.tenant_id == tid,
                                                       DocumentFolder.name.like("Sample:%")))


async def _bulk(session, model, rows):
    for s in range(0, len(rows), 1000):
        await session.execute(insert(model), rows[s : s + 1000])


async def seed(count: int, email: str, clear_only: bool) -> None:
    async with session_scope(bypass_rls=True) as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        tid, uid = user.tenant_id, user.id
        poster = user.full_name or "Advocate"
        await _clear(session, tid)
        if clear_only:
            log.info("tenant_sample_cleared", tenant=str(tid))
            return

        matters, parties, hearings, tasks, notes = _matter_rows(count, tid, uid)
        await _bulk(session, Matter, matters)
        await _bulk(session, MatterParty, parties)
        await _bulk(session, Hearing, hearings)
        await _bulk(session, MatterTask, tasks)
        await _bulk(session, MatterNote, notes)
        log.info("matters_seeded", matters=len(matters), parties=len(parties),
                 hearings=len(hearings), tasks=len(tasks), notes=len(notes))

        leads, acts = _lead_rows(count, tid, uid)
        await _bulk(session, Lead, leads)
        await _bulk(session, LeadActivity, acts)
        log.info("leads_seeded", leads=len(leads), activities=len(acts))

        await _bulk(session, KnowledgeItem, _knowledge_rows(count, tid, uid))
        log.info("knowledge_seeded", count=count)

        await _bulk(session, Listing, _listing_rows(count, tid, uid, poster))
        log.info("marketplace_seeded", count=count)

        invoices, items = _invoice_rows(count, tid, uid)
        await _bulk(session, Invoice, invoices)
        await _bulk(session, InvoiceLineItem, items)
        log.info("invoices_seeded", invoices=len(invoices), line_items=len(items))

        await _bulk(session, CalendarEvent, _event_rows(count, tid, uid))
        log.info("calendar_seeded", count=count)

        folders, docs, versions = _document_rows(count, tid, uid)
        await _bulk(session, DocumentFolder, folders)
        await _bulk(session, Document, docs)
        await _bulk(session, DocumentVersion, versions)
        log.info("documents_seeded", folders=len(folders), documents=len(docs))

        payments = _payment_rows(count, tid, uid, [inv["id"] for inv in invoices])
        await _bulk(session, Payment, payments)
        log.info("payments_seeded", count=len(payments))


def main() -> None:
    p = argparse.ArgumentParser(description="Seed sample tenant data.")
    p.add_argument("--count", type=int, default=5000, help="Rows per section (default 5000).")
    p.add_argument("--email", default="ds@simsononline.com", help="Seed into this user's tenant.")
    p.add_argument("--clear", action="store_true", help="Remove sample rows and exit.")
    args = p.parse_args()
    asyncio.run(seed(args.count, args.email, args.clear))


if __name__ == "__main__":  # pragma: no cover
    main()
