"""Timesheet workflow, spreadsheet parsing, rate resolution and billing."""

from __future__ import annotations

import csv
import re
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from xml.etree import ElementTree

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.modules.billing.models import TimeEntry, TimeEntrySource, TimeEntryStatus
from app.modules.billing.schemas import (
    InvoiceCreate,
    LineItemCreate,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryUpdate,
    TimeImportRow,
    TimeInvoiceCreate,
)
from app.modules.clients.models import Client
from app.modules.identity.models import User
from app.modules.matters.models import Matter, MatterFeeArrangement, MatterTeamMember, RateBasis
from app.modules.rates.models import CounselRate

_CENT = Decimal("0.01")
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_HEADERS = {
    "date": "work_date",
    "work date": "work_date",
    "counsel email": "counsel_email",
    "email": "counsel_email",
    "matter": "matter_number",
    "matter number": "matter_number",
    "client": "client_name",
    "client name": "client_name",
    "hours": "hours",
    "duration": "hours",
    "description": "description",
    "work description": "description",
    "activity": "activity_type",
    "activity type": "activity_type",
    "billable": "billable",
}


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    value = 0
    for char in letters.group(0) if letters else "A":
        value = value * 26 + ord(char) - 64
    return value - 1


def spreadsheet_rows(data: bytes, filename: str) -> list[list[str]]:
    """Read the first CSV/XLSX worksheet without executing macros or formulas."""
    if filename.lower().endswith(".csv"):
        text = data.decode("utf-8-sig")
        return [[cell.strip() for cell in row] for row in csv.reader(StringIO(text))]
    if not filename.lower().endswith(".xlsx"):
        raise ValidationError("Upload an Excel .xlsx or .csv timesheet.")
    try:
        with zipfile.ZipFile(BytesIO(data)) as book:
            if sum(item.file_size for item in book.infolist()) > 10 * 1024 * 1024:
                raise ValidationError("The expanded Excel workbook is too large.")
            shared: list[str] = []
            if "xl/sharedStrings.xml" in book.namelist():
                shared_xml = book.read("xl/sharedStrings.xml")
                if b"<!DOCTYPE" in shared_xml.upper() or b"<!ENTITY" in shared_xml.upper():
                    raise ValidationError("The Excel workbook contains unsafe XML.")
                root = ElementTree.fromstring(shared_xml)  # noqa: S314 -- DTD/entities rejected
                shared = [
                    "".join(node.text or "" for node in item.findall(".//m:t", _NS))
                    for item in root.findall("m:si", _NS)
                ]
            sheet_xml = book.read("xl/worksheets/sheet1.xml")
            if b"<!DOCTYPE" in sheet_xml.upper() or b"<!ENTITY" in sheet_xml.upper():
                raise ValidationError("The Excel workbook contains unsafe XML.")
            sheet = ElementTree.fromstring(sheet_xml)  # noqa: S314 -- DTD/entities rejected
            out: list[list[str]] = []
            for row in sheet.findall(".//m:sheetData/m:row", _NS):
                cells: dict[int, str] = {}
                for cell in row.findall("m:c", _NS):
                    idx = _column_index(cell.get("r", "A1"))
                    kind = cell.get("t")
                    value_node = cell.find("m:v", _NS)
                    if kind == "inlineStr":
                        value = "".join(n.text or "" for n in cell.findall(".//m:t", _NS))
                    else:
                        value = (
                            value_node.text if value_node is not None and value_node.text else ""
                        )
                        if kind == "s" and value.isdigit() and int(value) < len(shared):
                            value = shared[int(value)]
                    cells[idx] = value.strip()
                out.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
            return out
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as exc:
        raise ValidationError(
            "The Excel workbook could not be read. Use the supplied template."
        ) from exc


def _date(value: str) -> date | None:
    raw = value.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        serial = int(float(raw))
        return date(1899, 12, 30) + timedelta(days=serial)
    except (ValueError, OverflowError):
        return None


def normalise_rows(data: bytes, filename: str) -> list[TimeImportRow]:
    rows = spreadsheet_rows(data, filename)
    if not rows:
        raise ValidationError("The spreadsheet is empty.")
    if len(rows) > 1001:
        raise ValidationError("Import at most 1,000 time rows in one spreadsheet.")
    columns = {_HEADERS.get(value.strip().lower(), ""): i for i, value in enumerate(rows[0])}
    required = ("work_date", "hours", "description")
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValidationError(f"Missing required columns: {', '.join(missing)}.")
    result: list[TimeImportRow] = []
    for number, values in enumerate(rows[1:], 2):

        def get(key: str, row_values: list[str] = values) -> str:
            idx = columns.get(key, -1)
            return row_values[idx].strip() if 0 <= idx < len(row_values) else ""

        if not any(values):
            continue
        errors: list[str] = []
        worked = _date(get("work_date"))
        if worked is None:
            errors.append("Invalid date; use DD/MM/YYYY.")
        try:
            minutes = int((Decimal(get("hours")) * 60).quantize(Decimal("1")))
            if minutes < 1 or minutes > 1440:
                raise ValueError
        except (InvalidOperation, ValueError):
            minutes = 0
            errors.append("Hours must be greater than 0 and no more than 24.")
        description = get("description")
        if len(description) < 2:
            errors.append("Description is required.")
        flag = get("billable").lower()
        result.append(
            TimeImportRow(
                row_number=number,
                work_date=worked,
                counsel_email=get("counsel_email"),
                matter_number=get("matter_number"),
                client_name=get("client_name"),
                duration_minutes=minutes,
                description=description,
                activity_type=get("activity_type") or "Professional work",
                billable=flag not in {"no", "n", "false", "0"},
                errors=errors,
            )
        )
    return result


class TimesheetService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session, self.user_id, self.tenant_id = session, user_id, tenant_id

    async def _context(
        self, matter_id: uuid.UUID | None, client_id: uuid.UUID | None
    ) -> tuple[Matter | None, Client | None]:
        matter = None
        if matter_id:
            matter = await self.session.scalar(
                select(Matter).where(
                    Matter.id == matter_id,
                    Matter.tenant_id == self.tenant_id,
                    Matter.deleted_at.is_(None),
                )
            )
            if not matter:
                raise NotFoundError("Matter not found.")
            client_id = client_id or matter.client_id
        client = None
        if client_id:
            client = await self.session.scalar(
                select(Client).where(
                    Client.id == client_id,
                    Client.tenant_id == self.tenant_id,
                    Client.deleted_at.is_(None),
                )
            )
            if not client:
                raise NotFoundError("Client not found.")
        if not matter and not client:
            raise ValidationError("Select a matter or client for the time entry.")
        if matter and client and matter.client_id and matter.client_id != client.id:
            raise ValidationError("The selected client does not belong to this matter.")
        return matter, client

    async def _rate(self, user_id: uuid.UUID, worked: date, matter: Matter | None) -> Decimal:
        if matter:
            team = await self.session.scalar(
                select(MatterTeamMember)
                .where(
                    MatterTeamMember.tenant_id == self.tenant_id,
                    MatterTeamMember.matter_id == matter.id,
                    MatterTeamMember.user_id == user_id,
                    MatterTeamMember.deleted_at.is_(None),
                    MatterTeamMember.from_date <= worked,
                    or_(MatterTeamMember.to_date.is_(None), MatterTeamMember.to_date >= worked),
                )
                .order_by(MatterTeamMember.from_date.desc())
            )
            if team and team.rate_basis == RateBasis.HOURLY and team.rate_amount is not None:
                return Decimal(team.rate_amount)
        card = await self.session.scalar(
            select(CounselRate)
            .where(
                CounselRate.tenant_id == self.tenant_id,
                CounselRate.user_id == user_id,
                CounselRate.basis == RateBasis.HOURLY,
                CounselRate.deleted_at.is_(None),
                CounselRate.effective_from <= worked,
                or_(CounselRate.effective_to.is_(None), CounselRate.effective_to >= worked),
            )
            .order_by(CounselRate.effective_from.desc())
        )
        if card:
            return Decimal(card.amount)
        if matter:
            arrangement = await self.session.scalar(
                select(MatterFeeArrangement)
                .where(
                    MatterFeeArrangement.tenant_id == self.tenant_id,
                    MatterFeeArrangement.matter_id == matter.id,
                    MatterFeeArrangement.deleted_at.is_(None),
                    MatterFeeArrangement.effective_from <= worked,
                    or_(
                        MatterFeeArrangement.effective_to.is_(None),
                        MatterFeeArrangement.effective_to >= worked,
                    ),
                )
                .order_by(MatterFeeArrangement.effective_from.desc())
            )
            if arrangement and arrangement.hourly_rate is not None:
                return Decimal(arrangement.hourly_rate)
        return Decimal(0)

    async def create(
        self,
        data: TimeEntryCreate,
        *,
        user_id: uuid.UUID | None = None,
        source: TimeEntrySource = TimeEntrySource.MANUAL,
        batch: str | None = None,
    ) -> TimeEntry:
        owner = user_id or self.user_id
        matter, client = await self._context(data.matter_id, data.client_id)
        rate = await self._rate(owner, data.work_date, matter) if data.billable else Decimal(0)
        amount = (rate * Decimal(data.duration_minutes) / Decimal(60)).quantize(_CENT)
        entry = TimeEntry(
            tenant_id=self.tenant_id,
            user_id=owner,
            matter_id=matter.id if matter else None,
            client_id=client.id if client else (matter.client_id if matter else None),
            work_date=data.work_date,
            duration_minutes=data.duration_minutes,
            description=data.description.strip(),
            activity_type=data.activity_type.strip(),
            billable=data.billable,
            hourly_rate=rate,
            amount=amount,
            source=source,
            import_batch=batch,
            created_by=self.user_id,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list(
        self, *, all_users: bool, status: TimeEntryStatus | None = None
    ) -> list[TimeEntryRead]:
        stmt = select(TimeEntry).where(
            TimeEntry.tenant_id == self.tenant_id, TimeEntry.deleted_at.is_(None)
        )
        if not all_users:
            stmt = stmt.where(TimeEntry.user_id == self.user_id)
        if status:
            stmt = stmt.where(TimeEntry.status == status)
        entries = list(
            (
                await self.session.scalars(
                    stmt.order_by(TimeEntry.work_date.desc(), TimeEntry.created_at.desc()).limit(
                        1000
                    )
                )
            ).all()
        )
        user_ids = {e.user_id for e in entries}
        matter_ids = {e.matter_id for e in entries if e.matter_id}
        client_ids = {e.client_id for e in entries if e.client_id}
        users = (
            {
                u.id: u.full_name
                for u in (
                    await self.session.scalars(select(User).where(User.id.in_(user_ids)))
                ).all()
            }
            if user_ids
            else {}
        )
        matters = (
            {
                m.id: m.matter_number
                for m in (
                    await self.session.scalars(select(Matter).where(Matter.id.in_(matter_ids)))
                ).all()
            }
            if matter_ids
            else {}
        )
        clients = (
            {
                c.id: c.display_name
                for c in (
                    await self.session.scalars(select(Client).where(Client.id.in_(client_ids)))
                ).all()
            }
            if client_ids
            else {}
        )
        return [
            TimeEntryRead.model_validate(
                {
                    **{
                        name: getattr(e, name)
                        for name in TimeEntryRead.model_fields
                        if hasattr(e, name)
                    },
                    "counsel_name": users.get(e.user_id, "Counsel"),
                    "matter_number": matters.get(e.matter_id),
                    "client_name": clients.get(e.client_id),
                }
            )
            for e in entries
        ]

    async def _entry(self, entry_id: uuid.UUID) -> TimeEntry:
        entry = await self.session.scalar(
            select(TimeEntry).where(
                TimeEntry.id == entry_id,
                TimeEntry.tenant_id == self.tenant_id,
                TimeEntry.deleted_at.is_(None),
            )
        )
        if not entry:
            raise NotFoundError("Time entry not found.")
        return entry

    async def submit(self, entry_id: uuid.UUID) -> TimeEntry:
        entry = await self._entry(entry_id)
        if entry.user_id != self.user_id or entry.status not in (
            TimeEntryStatus.DRAFT,
            TimeEntryStatus.REJECTED,
        ):
            raise ValidationError("Only your draft or rejected time can be submitted.")
        entry.status, entry.submitted_at, entry.rejection_reason = (
            TimeEntryStatus.SUBMITTED,
            datetime.now(UTC),
            None,
        )
        return entry

    async def update(self, entry_id: uuid.UUID, data: TimeEntryUpdate) -> TimeEntry:
        entry = await self._entry(entry_id)
        if entry.user_id != self.user_id or entry.status not in (
            TimeEntryStatus.DRAFT,
            TimeEntryStatus.REJECTED,
        ):
            raise ValidationError("Only your draft or rejected time can be edited.")
        values = data.model_dump(exclude_unset=True)
        matter_id = values.get("matter_id", entry.matter_id)
        client_id = values.get("client_id", entry.client_id)
        matter, client = await self._context(matter_id, client_id)
        entry.matter_id = matter.id if matter else None
        entry.client_id = client.id if client else (matter.client_id if matter else None)
        for field in ("work_date", "duration_minutes", "description", "activity_type", "billable"):
            if field in values:
                setattr(entry, field, values[field])
        entry.hourly_rate = (
            await self._rate(entry.user_id, entry.work_date, matter)
            if entry.billable
            else Decimal(0)
        )
        entry.amount = (entry.hourly_rate * Decimal(entry.duration_minutes) / Decimal(60)).quantize(
            _CENT
        )
        entry.status, entry.rejection_reason = TimeEntryStatus.DRAFT, None
        return entry

    async def delete(self, entry_id: uuid.UUID) -> None:
        entry = await self._entry(entry_id)
        if entry.user_id != self.user_id or entry.status not in (
            TimeEntryStatus.DRAFT,
            TimeEntryStatus.REJECTED,
        ):
            raise ValidationError("Only your draft or rejected time can be deleted.")
        entry.deleted_at = datetime.now(UTC)

    async def approve(self, ids: list[uuid.UUID], *, reject_reason: str | None = None) -> None:
        if not ids:
            raise ValidationError("Select at least one time entry.")
        entries = list(
            (
                await self.session.scalars(
                    select(TimeEntry)
                    .where(
                        TimeEntry.id.in_(ids),
                        TimeEntry.tenant_id == self.tenant_id,
                        TimeEntry.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
            ).all()
        )
        if len(entries) != len(set(ids)) or any(
            e.status != TimeEntryStatus.SUBMITTED for e in entries
        ):
            raise ValidationError("Only submitted, unbilled time can be reviewed.")
        now = datetime.now(UTC)
        for entry in entries:
            if reject_reason:
                entry.status, entry.rejection_reason = TimeEntryStatus.REJECTED, reject_reason
            else:
                if entry.billable and entry.hourly_rate <= 0:
                    raise ValidationError(
                        "Set an hourly rate for every billable counsel/matter before approval."
                    )
                entry.status, entry.approved_at, entry.approved_by = (
                    TimeEntryStatus.APPROVED,
                    now,
                    self.user_id,
                )

    async def invoice(self, data: TimeInvoiceCreate):
        from app.modules.billing.service import BillingService

        entries = list(
            (
                await self.session.scalars(
                    select(TimeEntry)
                    .where(
                        TimeEntry.id.in_(data.entry_ids),
                        TimeEntry.tenant_id == self.tenant_id,
                        TimeEntry.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
            ).all()
        )
        if len(entries) != len(set(data.entry_ids)) or any(
            e.status != TimeEntryStatus.APPROVED or e.invoice_id for e in entries
        ):
            raise ValidationError(
                "Every selected entry must be approved and not previously billed."
            )
        if any(not e.billable for e in entries):
            raise ValidationError("Non-billable time cannot be invoiced.")
        client_ids = {e.client_id for e in entries}
        if len(client_ids) != 1 or None in client_ids:
            raise ValidationError(
                "Create one invoice at a time for entries belonging to the same client."
            )
        client = await self.session.scalar(
            select(Client).where(
                Client.id == next(iter(client_ids)), Client.tenant_id == self.tenant_id
            )
        )
        if not client:
            raise NotFoundError("Client not found.")
        matter_ids = {e.matter_id for e in entries}
        common_matter = next(iter(matter_ids)) if len(matter_ids) == 1 else None
        users = {
            u.id: u.full_name
            for u in (
                await self.session.scalars(
                    select(User).where(User.id.in_({e.user_id for e in entries}))
                )
            ).all()
        }
        items = [
            LineItemCreate(
                description=(
                    f"{e.work_date.strftime('%d/%m/%Y')} · "
                    f"{users.get(e.user_id, 'Counsel')} · {e.description}"
                ),
                quantity=(Decimal(e.duration_minutes) / Decimal(60)).quantize(Decimal("0.01")),
                unit_price=e.hourly_rate,
            )
            for e in entries
        ]
        invoice = await BillingService(self.session, self.user_id, self.tenant_id).create_invoice(
            InvoiceCreate(
                client_name=client.display_name,
                client_id=client.id,
                matter_id=common_matter,
                due_date=data.due_date,
                tax_rate=data.tax_rate,
                notes=data.notes,
                document_type=data.document_type,
                line_items=items,
            )
        )
        for entry in entries:
            entry.status, entry.invoice_id = TimeEntryStatus.BILLED, invoice.id
        await self.session.flush()
        return invoice

    async def resolve_import(
        self, rows: list[TimeImportRow], *, create: bool
    ) -> tuple[list[TimeImportRow], list[TimeEntry]]:
        emails = {r.counsel_email.lower() for r in rows if r.counsel_email}
        numbers = {r.matter_number.lower() for r in rows if r.matter_number}
        names = {r.client_name.lower() for r in rows if r.client_name}
        users = {
            u.email.lower(): u
            for u in (
                await self.session.scalars(
                    select(User).where(User.tenant_id == self.tenant_id, User.deleted_at.is_(None))
                )
            ).all()
            if u.email and u.email.lower() in emails
        }
        matters = {
            m.matter_number.lower(): m
            for m in (
                await self.session.scalars(
                    select(Matter).where(
                        Matter.tenant_id == self.tenant_id, Matter.deleted_at.is_(None)
                    )
                )
            ).all()
            if m.matter_number.lower() in numbers
        }
        clients = {
            c.display_name.lower(): c
            for c in (
                await self.session.scalars(
                    select(Client).where(
                        Client.tenant_id == self.tenant_id, Client.deleted_at.is_(None)
                    )
                )
            ).all()
            if c.display_name.lower() in names
        }
        made: list[TimeEntry] = []
        batch = uuid.uuid4().hex[:16]
        for row in rows:
            errors = list(row.errors)
            user = (
                users.get(row.counsel_email.lower())
                if row.counsel_email
                else await self.session.get(User, self.user_id)
            )
            matter = matters.get(row.matter_number.lower()) if row.matter_number else None
            client = clients.get(row.client_name.lower()) if row.client_name else None
            if not user:
                errors.append("Counsel email was not found in this firm.")
            if row.matter_number and not matter:
                errors.append("Matter number was not found.")
            if row.client_name and not client:
                errors.append("Client name was not found.")
            if not matter and not client:
                errors.append("Provide a valid matter number or client name.")
            row.errors = errors
            if create and not errors and row.work_date and user:
                entry = await self.create(
                    TimeEntryCreate(
                        matter_id=matter.id if matter else None,
                        client_id=client.id if client else None,
                        work_date=row.work_date,
                        duration_minutes=row.duration_minutes,
                        description=row.description,
                        activity_type=row.activity_type,
                        billable=row.billable,
                    ),
                    user_id=user.id,
                    source=TimeEntrySource.IMPORT,
                    batch=batch,
                )
                entry.status, entry.submitted_at = TimeEntryStatus.SUBMITTED, datetime.now(UTC)
                made.append(entry)
        return rows, made
