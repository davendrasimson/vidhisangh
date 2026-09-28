"""Create and remove a small, useful sample workspace for a tenant.

Every created root row and stored object key is recorded in ``Tenant.settings``.
Deletion uses those exact UUIDs, never names or broad tag matching, so user data
that happens to contain the word "sample" cannot be removed.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import Storage
from app.modules.billing.models import Invoice, InvoiceFollowUp, InvoiceLineItem
from app.modules.calendar.models import CalendarEvent
from app.modules.clients.models import Client, ClientKind
from app.modules.crm.models import Lead, LeadActivity
from app.modules.documents.models import Document, DocumentFolder, DocumentVersion
from app.modules.knowledge.models import KnowledgeItem
from app.modules.marketplace.models import Listing
from app.modules.matters.models import Hearing, Matter, MatterNote, MatterParty, MatterTask
from app.modules.payments.models import Payment
from app.modules.tenancy.models import Tenant

SETTING_KEY = "sample_data"


class SampleDataService:
    def __init__(
        self, session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, storage: Storage
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.storage = storage

    async def _tenant(self) -> Tenant:
        tenant = await self.session.get(Tenant, self.tenant_id)
        if tenant is None:
            raise RuntimeError("Tenant not found.")
        return tenant

    async def status(self) -> dict:
        tenant = await self._tenant()
        manifest = (tenant.settings or {}).get(SETTING_KEY) or {}
        entities = manifest.get("entities") or {}
        return {
            "available": bool(manifest.get("active")),
            "counts": {name: len(ids) for name, ids in entities.items() if ids},
        }

    async def create(self) -> dict:
        tenant = await self._tenant()
        current = (tenant.settings or {}).get(SETTING_KEY) or {}
        if current.get("active"):
            return await self.status()

        today = date.today()
        now = datetime.now(UTC)
        entities: dict[str, list[str]] = {}

        def remember(name: str, *rows) -> None:
            entities[name] = [str(row.id) for row in rows]

        client = Client(
            tenant_id=self.tenant_id,
            kind=ClientKind.INDIVIDUAL,
            display_name="Aarav Sharma (Sample)",
            first_name="Aarav",
            last_name="Sharma",
            email="aarav.sample@example.invalid",
            city="New Delhi",
            state="Delhi",
            notes="Sample client for exploring VidhiSangh.",
            tags=["vidhisangh-sample"],
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.session.add(client)
        await self.session.flush()
        remember("clients", client)

        matter_specs = [
            (
                "SAMPLE/2026/001",
                "Aarav Sharma v. Sunrise Builders Pvt. Ltd.",
                "Consumer Protection",
                "District Consumer Commission, New Delhi",
                "arguments",
                "high",
            ),
            (
                "SAMPLE/2026/002",
                "Meera Textiles — Contract Review",
                "Corporate & Commercial",
                None,
                "pleadings",
                "medium",
            ),
            (
                "SAMPLE/2026/003",
                "State v. Rohan Verma",
                "Criminal Defence",
                "District & Sessions Court, Saket",
                "evidence",
                "high",
            ),
        ]
        matters: list[Matter] = []
        for number, title, area, court, stage, priority in matter_specs:
            matter = Matter(
                tenant_id=self.tenant_id,
                matter_number=number,
                title=title,
                client_id=client.id,
                client_name=client.display_name,
                matter_type="litigation",
                status="open",
                stage=stage,
                priority=priority,
                practice_area=area,
                court=court,
                description="Sample matter with connected hearings, tasks, notes and documents.",
                opened_on=today - timedelta(days=45),
                assigned_to=self.user_id,
                created_by=self.user_id,
            )
            self.session.add(matter)
            matters.append(matter)
        await self.session.flush()
        remember("matters", *matters)

        for index, matter in enumerate(matters):
            self.session.add_all(
                [
                    MatterParty(
                        tenant_id=self.tenant_id,
                        matter_id=matter.id,
                        name=matter.client_name,
                        role="Petitioner",
                        side="ours",
                        position=1,
                    ),
                    MatterParty(
                        tenant_id=self.tenant_id,
                        matter_id=matter.id,
                        name="Opposing Party (Sample)",
                        role="Respondent",
                        side="opposing",
                        position=1,
                    ),
                    Hearing(
                        tenant_id=self.tenant_id,
                        matter_id=matter.id,
                        scheduled_on=now + timedelta(days=4 + index * 5),
                        court=matter.court,
                        purpose="Arguments" if index == 0 else "Directions",
                        status="scheduled",
                        notes="Sample hearing",
                    ),
                    MatterTask(
                        tenant_id=self.tenant_id,
                        matter_id=matter.id,
                        title="Prepare hearing brief",
                        due_on=today + timedelta(days=2 + index),
                        status="open",
                        assigned_to=self.user_id,
                    ),
                    MatterNote(
                        tenant_id=self.tenant_id,
                        matter_id=matter.id,
                        author_id=self.user_id,
                        body=(
                            "Sample note: confirm instructions and update the chronology "
                            "before the next date."
                        ),
                    ),
                ]
            )

        events = [
            CalendarEvent(
                tenant_id=self.tenant_id,
                title=f"Hearing: {m.title}",
                description="Sample calendar event",
                event_type="court",
                start_at=now + timedelta(days=4 + i * 5),
                end_at=now + timedelta(days=4 + i * 5, hours=1),
                location=m.court,
                matter_id=m.id,
                assigned_to=self.user_id,
                created_by=self.user_id,
            )
            for i, m in enumerate(matters)
        ]
        self.session.add_all(events)
        await self.session.flush()
        remember("calendar", *events)

        lead = Lead(
            tenant_id=self.tenant_id,
            name="Kavya Industries (Sample Lead)",
            email="kavya.sample@example.invalid",
            source="referral",
            status="contacted",
            practice_area="Employment & Labour",
            notes="Needs advice on employment contracts.",
            estimated_value=Decimal("75000"),
            assigned_to=self.user_id,
            created_by=self.user_id,
        )
        self.session.add(lead)
        await self.session.flush()
        activity = LeadActivity(
            tenant_id=self.tenant_id,
            lead_id=lead.id,
            type="call",
            subject="Introductory call",
            body="Sample follow-up: send scope and fee proposal.",
            due_on=today + timedelta(days=2),
            completed=False,
            created_by=self.user_id,
        )
        self.session.add(activity)
        remember("leads", lead)

        resources = [
            KnowledgeItem(
                tenant_id=self.tenant_id,
                title="Sample checklist: First client conference",
                category="checklist",
                body=(
                    "1. Conflict check\n2. Identify limitation\n3. Collect documents\n"
                    "4. Confirm scope and fees"
                ),
                practice_area="General Practice",
                tags=["vidhisangh-sample", "intake"],
                created_by=self.user_id,
            ),
            KnowledgeItem(
                tenant_id=self.tenant_id,
                title="Sample research note: Interim relief",
                category="note",
                body=(
                    "Record the facts, statutory provision, controlling authorities and the "
                    "precise relief sought."
                ),
                practice_area="Civil Litigation",
                tags=["vidhisangh-sample", "research"],
                created_by=self.user_id,
            ),
        ]
        self.session.add_all(resources)
        await self.session.flush()
        remember("knowledge", *resources)

        invoice = Invoice(
            tenant_id=self.tenant_id,
            invoice_number="SAMPLE-PI-001",
            document_type="proforma",
            client_name=client.display_name,
            client_id=client.id,
            matter_id=matters[0].id,
            status="sent",
            issue_date=today,
            due_date=today + timedelta(days=7),
            currency="INR",
            tax_rate=Decimal("18"),
            subtotal=Decimal("25000"),
            tax_amount=Decimal("4500"),
            total=Decimal("29500"),
            amount_paid=Decimal("0"),
            notes="Sample proforma invoice.",
            verification_code=f"SMP{secrets.token_hex(6).upper()}",
            payment_token=secrets.token_urlsafe(32),
            next_follow_up_on=today + timedelta(days=3),
            created_by=self.user_id,
        )
        self.session.add(invoice)
        await self.session.flush()
        self.session.add_all(
            [
                InvoiceLineItem(
                    tenant_id=self.tenant_id,
                    invoice_id=invoice.id,
                    description="Professional fee — initial stage",
                    quantity=1,
                    unit_price=Decimal("25000"),
                    amount=Decimal("25000"),
                ),
                InvoiceFollowUp(
                    tenant_id=self.tenant_id,
                    invoice_id=invoice.id,
                    channel="email",
                    remark="Sample reminder sent with payment link.",
                    outcome="Awaiting confirmation",
                    next_follow_up_on=today + timedelta(days=3),
                    created_by=self.user_id,
                ),
            ]
        )
        remember("invoices", invoice)

        payment = Payment(
            tenant_id=self.tenant_id,
            amount=1500000,
            currency="INR",
            status="paid",
            provider="mock",
            provider_order_id=f"order_sample_{uuid.uuid4().hex[:12]}",
            provider_payment_id=f"pay_sample_{uuid.uuid4().hex[:12]}",
            receipt="SAMPLE-RCPT-001",
            description="Sample fee receipt",
            matter_id=matters[1].id,
            created_by=self.user_id,
            paid_at=now - timedelta(days=3),
        )
        self.session.add(payment)
        await self.session.flush()
        remember("payments", payment)

        listing = Listing(
            type="local_counsel",
            title="Sample: Local counsel required in Jaipur",
            description="Sample marketplace listing for a procedural hearing. [vidhisangh-sample]",
            practice_area="Civil Litigation",
            location="Jaipur",
            budget=Decimal("15000"),
            status="open",
            posted_by=self.user_id,
            poster_name="Sample workspace",
            poster_tenant_id=self.tenant_id,
            matter_id=matters[0].id,
        )
        self.session.add(listing)
        await self.session.flush()
        remember("marketplace", listing)

        folder = DocumentFolder(
            tenant_id=self.tenant_id,
            name="Sample matter documents",
            matter_id=matters[0].id,
            created_by=self.user_id,
        )
        self.session.add(folder)
        await self.session.flush()
        storage_keys: list[str] = []
        documents: list[Document] = []
        for filename, body in [
            (
                "Sample case chronology.txt",
                "SAMPLE DOCUMENT\n\n01/08/2026 — Client engagement\n"
                "15/08/2026 — Notice issued\n"
                "28/09/2026 — Next action: prepare hearing brief\n",
            ),
            (
                "Sample client instructions.txt",
                "SAMPLE DOCUMENT\n\nReview the agreement, payment schedule and "
                "correspondence before advice.\n",
            ),
        ]:
            document = Document(
                tenant_id=self.tenant_id,
                name=filename,
                folder_id=folder.id,
                matter_id=matters[0].id,
                client_id=client.id,
                content_type="text/plain",
                size=0,
                tags=["vidhisangh-sample"],
                version_count=0,
                uploaded_by=self.user_id,
            )
            self.session.add(document)
            await self.session.flush()
            raw = body.encode()
            key = f"{self.tenant_id}/{document.id}/{uuid.uuid4().hex}"
            await self.storage.put(key, raw, "text/plain")
            version = DocumentVersion(
                tenant_id=self.tenant_id,
                document_id=document.id,
                version_no=1,
                storage_key=key,
                size=len(raw),
                content_type="text/plain",
                checksum=hashlib.sha256(raw).hexdigest(),
                comment="Generated sample file",
                uploaded_by=self.user_id,
            )
            self.session.add(version)
            await self.session.flush()
            document.current_version_id = version.id
            document.version_count = 1
            document.size = len(raw)
            storage_keys.append(key)
            documents.append(document)
        remember("documents", *documents)
        remember("folders", folder)

        settings = dict(tenant.settings or {})
        settings[SETTING_KEY] = {
            "active": True,
            "version": 1,
            "created_at": now.isoformat(),
            "entities": entities,
            "storage_keys": storage_keys,
        }
        tenant.settings = settings
        await self.session.flush()
        return await self.status()

    async def clear(self) -> dict:
        tenant = await self._tenant()
        manifest = (tenant.settings or {}).get(SETTING_KEY) or {}
        entities = manifest.get("entities") or {}

        def ids(name: str) -> list[uuid.UUID]:
            return [uuid.UUID(value) for value in entities.get(name, [])]

        for key in manifest.get("storage_keys") or []:
            await self.storage.delete(key)

        for model, name in [
            (Payment, "payments"),
            (CalendarEvent, "calendar"),
            (Listing, "marketplace"),
            (Document, "documents"),
            (DocumentFolder, "folders"),
            (Invoice, "invoices"),
            (Lead, "leads"),
            (KnowledgeItem, "knowledge"),
            (Matter, "matters"),
            (Client, "clients"),
        ]:
            values = ids(name)
            if values:
                await self.session.execute(delete(model).where(model.id.in_(values)))

        settings = dict(tenant.settings or {})
        settings.pop(SETTING_KEY, None)
        tenant.settings = settings
        await self.session.flush()
        return {"available": False, "counts": {}}
