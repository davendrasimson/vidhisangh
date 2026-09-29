"""Tenant-defined matter fields, secure values, and reporting summaries."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUserDep, TenantSessionDep, require_permission
from app.core.exceptions import ConflictError, NotFoundError, TenantError, ValidationError
from app.modules.audit.service import record_audit
from app.modules.matters.models import (
    Matter,
    MatterCustomField,
    MatterCustomSection,
    MatterCustomValue,
    MatterFieldType,
)


class StandardMatterSection(StrEnum):
    OVERVIEW = "overview"
    COURT_RECORD = "court_record"
    CLIENT_ENGAGEMENT = "client_engagement"
    DATES_DEADLINES = "dates_deadlines"
    ADDITIONAL = "additional"
    CUSTOM = "custom"


class SectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=400)
    position: int = Field(default=0, ge=0, le=10000)


class SectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=400)
    position: int | None = Field(default=None, ge=0, le=10000)


class SectionRead(SectionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class FieldCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    field_key: str | None = Field(default=None, max_length=80)
    section_key: StandardMatterSection = StandardMatterSection.ADDITIONAL
    custom_section_id: uuid.UUID | None = None
    help_text: str | None = Field(default=None, max_length=400)
    field_type: MatterFieldType = MatterFieldType.TEXT
    options: list[str] = Field(default_factory=list, max_length=100)
    is_required: bool = False
    is_encrypted: bool = False
    is_masked: bool = False
    is_reportable: bool = True
    position: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def validate_definition(self) -> FieldCreate:
        self.label = self.label.strip()
        if not self.label:
            raise ValueError("Field label cannot be blank.")
        self.options = list(dict.fromkeys(o.strip() for o in self.options if o.strip()))
        if (
            self.field_type in (MatterFieldType.DROPDOWN, MatterFieldType.MULTI_SELECT)
            and not self.options
        ):
            raise ValueError("Dropdown and multi-select fields need at least one option.")
        if self.section_key == StandardMatterSection.CUSTOM and not self.custom_section_id:
            raise ValueError("Select a custom section.")
        if self.section_key != StandardMatterSection.CUSTOM:
            self.custom_section_id = None
        if self.is_masked:
            self.is_encrypted = True
        if self.is_encrypted or self.is_masked:
            self.is_reportable = False
        return self


class FieldUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    section_key: StandardMatterSection | None = None
    custom_section_id: uuid.UUID | None = None
    help_text: str | None = Field(default=None, max_length=400)
    options: list[str] | None = Field(default=None, max_length=100)
    is_required: bool | None = None
    is_encrypted: bool | None = None
    is_masked: bool | None = None
    is_reportable: bool | None = None
    position: int | None = Field(default=None, ge=0, le=10000)


class FieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    section_key: str
    custom_section_id: uuid.UUID | None
    field_key: str
    label: str
    help_text: str | None
    field_type: MatterFieldType
    options: list[str]
    is_required: bool
    is_encrypted: bool
    is_masked: bool
    is_reportable: bool
    position: int


class FieldSettings(BaseModel):
    standard_sections: dict[str, str]
    sections: list[SectionRead]
    fields: list[FieldRead]


class ValueInput(BaseModel):
    field_id: uuid.UUID
    value: Any = None


class ValuesUpdate(BaseModel):
    values: list[ValueInput] = Field(max_length=300)


class ValueRead(BaseModel):
    field_id: uuid.UUID
    value: Any = None
    display_value: str | None = None
    has_value: bool = False
    masked: bool = False
    updated_at: datetime | None = None


class MatterFieldReport(BaseModel):
    field_id: uuid.UUID
    label: str
    field_type: MatterFieldType
    section: str
    total_matters: int
    populated: int
    missing: int
    completion_rate: float
    sum: float | None = None
    average: float | None = None
    values: list[dict[str, Any]] = Field(default_factory=list)
    sensitive: bool = False


STANDARD_SECTION_LABELS = {
    "overview": "Overview",
    "court_record": "Court record",
    "client_engagement": "Client & engagement",
    "dates_deadlines": "Dates & deadlines",
    "additional": "Additional information",
}


def _slug(label: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:70]
    return value or "field"


def _stored(value: Any, field: MatterCustomField) -> str | None:
    if value is None or value == "" or value == []:
        return None
    kind = MatterFieldType(field.field_type)
    if kind == MatterFieldType.BOOLEAN:
        if not isinstance(value, bool):
            raise ValidationError(f"{field.label} must be yes or no.")
    elif kind in (MatterFieldType.NUMBER, MatterFieldType.AMOUNT):
        try:
            value = str(Decimal(str(value)))
        except InvalidOperation as exc:
            raise ValidationError(f"{field.label} must be a number.") from exc
    elif kind == MatterFieldType.DATE:
        try:
            value = date.fromisoformat(str(value)).isoformat()
        except ValueError as exc:
            raise ValidationError(f"{field.label} must be a valid date.") from exc
    elif kind == MatterFieldType.DROPDOWN and str(value) not in field.options:
        raise ValidationError(f"Select a valid option for {field.label}.")
    elif kind == MatterFieldType.MULTI_SELECT:
        if not isinstance(value, list) or any(str(v) not in field.options for v in value):
            raise ValidationError(f"Select valid options for {field.label}.")
        value = [str(v) for v in value]
    else:
        value = str(value).strip()
        if len(value) > 16000:
            raise ValidationError(f"{field.label} is too long.")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decoded(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


class MatterFieldService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session, self.user_id, self.tenant_id = session, user_id, tenant_id

    async def settings(self) -> FieldSettings:
        sections = list(
            (
                await self.session.scalars(
                    select(MatterCustomSection)
                    .where(
                        MatterCustomSection.tenant_id == self.tenant_id,
                        MatterCustomSection.deleted_at.is_(None),
                    )
                    .order_by(MatterCustomSection.position, MatterCustomSection.name)
                )
            ).all()
        )
        fields = list(
            (
                await self.session.scalars(
                    select(MatterCustomField)
                    .where(
                        MatterCustomField.tenant_id == self.tenant_id,
                        MatterCustomField.deleted_at.is_(None),
                    )
                    .order_by(
                        MatterCustomField.section_key,
                        MatterCustomField.position,
                        MatterCustomField.label,
                    )
                )
            ).all()
        )
        return FieldSettings(
            standard_sections=STANDARD_SECTION_LABELS,
            sections=[SectionRead.model_validate(x) for x in sections],
            fields=[FieldRead.model_validate(x) for x in fields],
        )

    async def create_section(self, data: SectionCreate) -> MatterCustomSection:
        name = data.name.strip()
        existing = await self.session.scalar(
            select(MatterCustomSection.id).where(
                MatterCustomSection.tenant_id == self.tenant_id,
                MatterCustomSection.deleted_at.is_(None),
                func.lower(MatterCustomSection.name) == name.lower(),
            )
        )
        if existing:
            raise ConflictError("A matter section with that name already exists.")
        row = MatterCustomSection(
            tenant_id=self.tenant_id,
            created_by=self.user_id,
            name=name,
            description=data.description,
            position=data.position,
        )
        self.session.add(row)
        await self.session.flush()
        self._audit("matter_field.section_created", f"Created matter section {name}", row.id)
        return row

    async def update_section(
        self, section_id: uuid.UUID, data: SectionUpdate
    ) -> MatterCustomSection:
        row = await self._section(section_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value.strip() if key == "name" and value else value)
        await self.session.flush()
        self._audit("matter_field.section_updated", f"Updated matter section {row.name}", row.id)
        return row

    async def delete_section(self, section_id: uuid.UUID) -> None:
        row = await self._section(section_id)
        used = await self.session.scalar(
            select(func.count()).where(
                MatterCustomField.tenant_id == self.tenant_id,
                MatterCustomField.deleted_at.is_(None),
                MatterCustomField.custom_section_id == row.id,
            )
        )
        if used:
            raise ConflictError("Move or remove the fields in this section first.")
        row.deleted_at = datetime.now(UTC)
        self._audit("matter_field.section_deleted", f"Removed matter section {row.name}", row.id)

    async def create_field(self, data: FieldCreate) -> MatterCustomField:
        if data.custom_section_id:
            await self._section(data.custom_section_id)
        base = _slug(data.field_key or data.label)
        key, suffix = base, 2
        while await self.session.scalar(
            select(MatterCustomField.id).where(
                MatterCustomField.tenant_id == self.tenant_id, MatterCustomField.field_key == key
            )
        ):
            key, suffix = f"{base}_{suffix}", suffix + 1
        row = MatterCustomField(
            tenant_id=self.tenant_id,
            created_by=self.user_id,
            field_key=key,
            **data.model_dump(exclude={"field_key"}),
        )
        self.session.add(row)
        await self.session.flush()
        self._audit(
            "matter_field.created",
            f"Created matter field {row.label}",
            row.id,
            {"encrypted": row.is_encrypted, "masked": row.is_masked},
        )
        return row

    async def update_field(self, field_id: uuid.UUID, data: FieldUpdate) -> MatterCustomField:
        row = await self._field(field_id)
        values = data.model_dump(exclude_unset=True)
        if "label" in values:
            values["label"] = values["label"].strip()
            if not values["label"]:
                raise ValidationError("Field label cannot be blank.")
        section_key = values.get("section_key", row.section_key)
        custom_id = values.get("custom_section_id", row.custom_section_id)
        if section_key == "custom":
            if not custom_id:
                raise ValidationError("Select a custom section.")
            await self._section(custom_id)
        else:
            values["custom_section_id"] = None
        if values.get("options") is not None:
            values["options"] = list(
                dict.fromkeys(x.strip() for x in values["options"] if x.strip())
            )
            if (
                row.field_type in (MatterFieldType.DROPDOWN, MatterFieldType.MULTI_SELECT)
                and not values["options"]
            ):
                raise ValidationError("Dropdown and multi-select fields need at least one option.")
        if values.get("is_masked"):
            values["is_encrypted"], values["is_reportable"] = True, False
        if row.is_encrypted and values.get("is_encrypted") is False:
            raise ValidationError("Encrypted matter fields cannot be converted to plain text.")
        resulting_encrypted = values.get("is_encrypted", row.is_encrypted)
        resulting_masked = values.get("is_masked", row.is_masked)
        if resulting_encrypted or resulting_masked:
            values["is_reportable"] = False
        # When encryption is switched on, migrate existing plaintext before changing the definition.
        if values.get("is_encrypted") and not row.is_encrypted:
            old_values = list(
                (
                    await self.session.scalars(
                        select(MatterCustomValue).where(
                            MatterCustomValue.tenant_id == self.tenant_id,
                            MatterCustomValue.field_id == row.id,
                            MatterCustomValue.deleted_at.is_(None),
                        )
                    )
                ).all()
            )
            for item in old_values:
                item.encrypted_value, item.plain_value = item.plain_value, None
        for key, value in values.items():
            setattr(row, key, value.strip() if key == "label" and value else value)
        await self.session.flush()
        self._audit("matter_field.updated", f"Updated matter field {row.label}", row.id)
        return row

    async def delete_field(self, field_id: uuid.UUID) -> None:
        row = await self._field(field_id)
        row.deleted_at = datetime.now(UTC)
        self._audit("matter_field.deleted", f"Removed matter field {row.label}", row.id)

    async def values(self, matter_id: uuid.UUID) -> list[ValueRead]:
        await self._matter(matter_id)
        settings = await self.settings()
        rows = list(
            (
                await self.session.scalars(
                    select(MatterCustomValue).where(
                        MatterCustomValue.tenant_id == self.tenant_id,
                        MatterCustomValue.matter_id == matter_id,
                        MatterCustomValue.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        by_id = {r.field_id: r for r in rows}
        output: list[ValueRead] = []
        for field in settings.fields:
            row = by_id.get(field.id)
            raw = (row.encrypted_value if field.is_encrypted else row.plain_value) if row else None
            value = _decoded(raw)
            has_value = value is not None and value != "" and value != []
            output.append(
                ValueRead(
                    field_id=field.id,
                    value=None if field.is_masked and has_value else value,
                    display_value="••••••••"
                    if field.is_masked and has_value
                    else (str(value) if has_value else None),
                    has_value=has_value,
                    masked=field.is_masked,
                    updated_at=row.updated_at if row else None,
                )
            )
        return output

    async def save_values(self, matter_id: uuid.UUID, data: ValuesUpdate) -> list[ValueRead]:
        await self._matter(matter_id)
        fields = {f.id: f for f in (await self.settings()).fields}
        if len({v.field_id for v in data.values}) != len(data.values):
            raise ValidationError("Each matter field may be submitted once.")
        rows = {
            r.field_id: r
            for r in (
                await self.session.scalars(
                    select(MatterCustomValue).where(
                        MatterCustomValue.tenant_id == self.tenant_id,
                        MatterCustomValue.matter_id == matter_id,
                        MatterCustomValue.deleted_at.is_(None),
                    )
                )
            ).all()
        }
        for item in data.values:
            spec = fields.get(item.field_id)
            if not spec:
                raise ValidationError("A submitted matter field is no longer available.")
            definition = await self._field(spec.id)
            stored = _stored(item.value, definition)
            row = rows.get(item.field_id)
            if row is None:
                row = MatterCustomValue(
                    tenant_id=self.tenant_id,
                    matter_id=matter_id,
                    field_id=item.field_id,
                    updated_by=self.user_id,
                )
                self.session.add(row)
                rows[item.field_id] = row
            row.updated_by = self.user_id
            if spec.is_encrypted:
                row.encrypted_value, row.plain_value = stored, None
            else:
                row.plain_value, row.encrypted_value = stored, None
        missing = [
            f.label for f in fields.values() if f.is_required and not self._has(rows.get(f.id), f)
        ]
        if missing:
            raise ValidationError(
                "Complete the required matter fields.", details={"fields": missing}
            )
        await self.session.flush()
        self._audit(
            "matter_field.values_updated",
            "Updated additional matter information",
            matter_id,
            {"field_count": len(data.values)},
        )
        return await self.values(matter_id)

    async def reveal(self, matter_id: uuid.UUID, field_id: uuid.UUID) -> ValueRead:
        await self._matter(matter_id)
        field = await self._field(field_id)
        row = await self.session.scalar(
            select(MatterCustomValue).where(
                MatterCustomValue.tenant_id == self.tenant_id,
                MatterCustomValue.matter_id == matter_id,
                MatterCustomValue.field_id == field_id,
                MatterCustomValue.deleted_at.is_(None),
            )
        )
        value = _decoded(
            row.encrypted_value if field.is_encrypted and row else row.plain_value if row else None
        )
        self._audit(
            "matter_field.value_revealed",
            f"Revealed masked field {field.label}",
            matter_id,
            {"field_id": str(field_id)},
        )
        return ValueRead(
            field_id=field_id,
            value=value,
            display_value=str(value) if value is not None else None,
            has_value=value is not None,
            masked=False,
            updated_at=row.updated_at if row else None,
        )

    async def report(self) -> list[MatterFieldReport]:
        settings = await self.settings()
        sections = {str(s.id): s.name for s in settings.sections}
        total = int(
            (
                await self.session.scalar(
                    select(func.count()).where(
                        Matter.tenant_id == self.tenant_id, Matter.deleted_at.is_(None)
                    )
                )
            )
            or 0
        )
        reports: list[MatterFieldReport] = []
        for field in settings.fields:
            rows = list(
                (
                    await self.session.scalars(
                        select(MatterCustomValue).where(
                            MatterCustomValue.tenant_id == self.tenant_id,
                            MatterCustomValue.field_id == field.id,
                            MatterCustomValue.deleted_at.is_(None),
                            MatterCustomValue.matter_id.in_(
                                select(Matter.id).where(
                                    Matter.tenant_id == self.tenant_id, Matter.deleted_at.is_(None)
                                )
                            ),
                        )
                    )
                ).all()
            )
            populated = sum(1 for r in rows if self._has(r, field))
            report = MatterFieldReport(
                field_id=field.id,
                label=field.label,
                field_type=field.field_type,
                section=sections.get(
                    str(field.custom_section_id),
                    STANDARD_SECTION_LABELS.get(field.section_key, "Additional information"),
                ),
                total_matters=total,
                populated=populated,
                missing=max(0, total - populated),
                completion_rate=round(populated / total, 4) if total else 0,
                sensitive=field.is_encrypted or field.is_masked,
            )
            if field.is_reportable and not report.sensitive:
                decoded = [_decoded(r.plain_value) for r in rows if self._has(r, field)]
                if field.field_type in (MatterFieldType.NUMBER, MatterFieldType.AMOUNT):
                    nums = [float(x) for x in decoded]
                    report.sum = round(sum(nums), 2)
                    report.average = round(sum(nums) / len(nums), 2) if nums else None
                elif field.field_type in (
                    MatterFieldType.DROPDOWN,
                    MatterFieldType.BOOLEAN,
                    MatterFieldType.MULTI_SELECT,
                ):
                    counts: dict[str, int] = {}
                    for value in decoded:
                        for item in value if isinstance(value, list) else [value]:
                            key = "Yes" if item is True else "No" if item is False else str(item)
                            counts[key] = counts.get(key, 0) + 1
                    report.values = [
                        {"key": k, "count": v}
                        for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:20]
                    ]
            reports.append(report)
        return reports

    async def _section(self, section_id: uuid.UUID) -> MatterCustomSection:
        row = await self.session.scalar(
            select(MatterCustomSection).where(
                MatterCustomSection.id == section_id,
                MatterCustomSection.tenant_id == self.tenant_id,
                MatterCustomSection.deleted_at.is_(None),
            )
        )
        if not row:
            raise NotFoundError("Matter section not found.")
        return row

    async def _field(self, field_id: uuid.UUID) -> MatterCustomField:
        row = await self.session.scalar(
            select(MatterCustomField).where(
                MatterCustomField.id == field_id,
                MatterCustomField.tenant_id == self.tenant_id,
                MatterCustomField.deleted_at.is_(None),
            )
        )
        if not row:
            raise NotFoundError("Matter field not found.")
        return row

    async def _matter(self, matter_id: uuid.UUID) -> Matter:
        row = await self.session.scalar(
            select(Matter).where(
                Matter.id == matter_id,
                Matter.tenant_id == self.tenant_id,
                Matter.deleted_at.is_(None),
            )
        )
        if not row:
            raise NotFoundError("Matter not found.")
        return row

    @staticmethod
    def _has(row: MatterCustomValue | None, field: FieldRead | MatterCustomField) -> bool:
        if not row:
            return False
        raw = row.encrypted_value if field.is_encrypted else row.plain_value
        value = _decoded(raw)
        return value is not None and value != "" and value != []

    def _audit(
        self, action: str, summary: str, entity_id: uuid.UUID, meta: dict | None = None
    ) -> None:
        record_audit(
            self.session,
            tenant_id=self.tenant_id,
            actor_id=self.user_id,
            action=action,
            summary=summary,
            entity_type="matter_custom_field",
            entity_id=str(entity_id),
            meta=meta,
        )


router = APIRouter(prefix="/matter-fields", tags=["Matter fields"])


def _svc(current: CurrentUserDep, session: TenantSessionDep) -> MatterFieldService:
    if current.tenant_id is None:
        raise TenantError("No tenant is associated with this session.")
    return MatterFieldService(session, current.id, current.tenant_id)


@router.get(
    "/settings", response_model=FieldSettings, dependencies=[require_permission("matter:read")]
)
async def get_settings(current: CurrentUserDep, session: TenantSessionDep) -> FieldSettings:
    return await _svc(current, session).settings()


@router.post(
    "/sections",
    response_model=SectionRead,
    status_code=201,
    dependencies=[require_permission("tenant:manage")],
)
async def add_section(
    data: SectionCreate, current: CurrentUserDep, session: TenantSessionDep
) -> SectionRead:
    return SectionRead.model_validate(await _svc(current, session).create_section(data))


@router.patch(
    "/sections/{section_id}",
    response_model=SectionRead,
    dependencies=[require_permission("tenant:manage")],
)
async def edit_section(
    section_id: uuid.UUID, data: SectionUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> SectionRead:
    return SectionRead.model_validate(await _svc(current, session).update_section(section_id, data))


@router.delete(
    "/sections/{section_id}", status_code=204, dependencies=[require_permission("tenant:manage")]
)
async def remove_section(
    section_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_section(section_id)
    return Response(status_code=204)


@router.post(
    "/fields",
    response_model=FieldRead,
    status_code=201,
    dependencies=[require_permission("tenant:manage")],
)
async def add_field(
    data: FieldCreate, current: CurrentUserDep, session: TenantSessionDep
) -> FieldRead:
    return FieldRead.model_validate(await _svc(current, session).create_field(data))


@router.patch(
    "/fields/{field_id}",
    response_model=FieldRead,
    dependencies=[require_permission("tenant:manage")],
)
async def edit_field(
    field_id: uuid.UUID, data: FieldUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> FieldRead:
    return FieldRead.model_validate(await _svc(current, session).update_field(field_id, data))


@router.delete(
    "/fields/{field_id}", status_code=204, dependencies=[require_permission("tenant:manage")]
)
async def remove_field(
    field_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> Response:
    await _svc(current, session).delete_field(field_id)
    return Response(status_code=204)


@router.get(
    "/matters/{matter_id}/values",
    response_model=list[ValueRead],
    dependencies=[require_permission("matter:read")],
)
async def get_values(
    matter_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> list[ValueRead]:
    return await _svc(current, session).values(matter_id)


@router.put(
    "/matters/{matter_id}/values",
    response_model=list[ValueRead],
    dependencies=[require_permission("matter:update")],
)
async def put_values(
    matter_id: uuid.UUID, data: ValuesUpdate, current: CurrentUserDep, session: TenantSessionDep
) -> list[ValueRead]:
    return await _svc(current, session).save_values(matter_id, data)


@router.get(
    "/matters/{matter_id}/values/{field_id}/reveal",
    response_model=ValueRead,
    dependencies=[require_permission("matter:update")],
)
async def reveal_value(
    matter_id: uuid.UUID, field_id: uuid.UUID, current: CurrentUserDep, session: TenantSessionDep
) -> ValueRead:
    return await _svc(current, session).reveal(matter_id, field_id)


@router.get(
    "/report",
    response_model=list[MatterFieldReport],
    dependencies=[require_permission("analytics:view")],
)
async def report(current: CurrentUserDep, session: TenantSessionDep) -> list[MatterFieldReport]:
    return await _svc(current, session).report()
