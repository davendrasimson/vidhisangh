"""Matters: Indian court record fields + advocates on both sides.

Revision ID: 0033_indian_court_matters
Revises: 0032_users_email_global_unique
Create Date: 2026-09-23

The matter model was court-agnostic (`court`, `case_number`, free text). Indian
litigation needs the structure the registries actually use:

* **CNR** — the 16-character Case Number Record eCourts assigns. It survives
  re-numbering on registration and transfer between courts, so it is the stable
  key to sync a matter against.
* **Filing vs registration** — a case is filed under one number and *registered*
  later under another; practitioners track both.
* **Court hierarchy + establishment** — Supreme Court / High Court / district /
  tribunal, plus the specific establishment, state and district.
* **Cause title, acts and sections** — how the registry indexes the case.
* **Next / last hearing and purpose** — the cause-list fields.

`matter_advocates` is new: counsel appearing for us and against us. Advocates are
modelled apart from parties because several advocates appear for one party, and
the same opposing counsel recurs across matters — which is the point of tracking
them.

All new columns are nullable, so existing matters are untouched and valid.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_indian_court_matters"
down_revision: str | None = "0032_users_email_global_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)

_MATTER_COLUMNS = [
    sa.Column("cnr_number", sa.String(16), nullable=True),
    sa.Column("case_type", sa.String(60), nullable=True),
    sa.Column("case_year", sa.Integer(), nullable=True),
    sa.Column("filing_number", sa.String(60), nullable=True),
    sa.Column("filing_date", sa.Date(), nullable=True),
    sa.Column("registration_number", sa.String(60), nullable=True),
    sa.Column("registration_date", sa.Date(), nullable=True),
    sa.Column("court_level", sa.String(20), nullable=True),
    sa.Column("court_establishment", sa.String(200), nullable=True),
    sa.Column("state", sa.String(80), nullable=True),
    sa.Column("district", sa.String(120), nullable=True),
    sa.Column("coram", sa.String(300), nullable=True),
    sa.Column("cause_title", sa.String(400), nullable=True),
    sa.Column("acts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    sa.Column("sections", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    sa.Column("next_hearing_date", sa.Date(), nullable=True),
    sa.Column("last_hearing_date", sa.Date(), nullable=True),
    sa.Column("hearing_purpose", sa.String(200), nullable=True),
    sa.Column("disposal_date", sa.Date(), nullable=True),
    sa.Column("disposal_nature", sa.String(160), nullable=True),
    sa.Column("ecourts_synced_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("ecourts_source", sa.String(60), nullable=True),
]


def upgrade() -> None:
    for column in _MATTER_COLUMNS:
        op.add_column("matters", column)
    op.create_index("ix_matters_cnr_number", "matters", ["cnr_number"])
    op.create_index("ix_matters_court_level", "matters", ["court_level"])
    op.create_index("ix_matters_next_hearing_date", "matters", ["next_hearing_date"])

    # Which side of the cause title a party sits on, and its printed position.
    op.add_column(
        "matter_parties",
        sa.Column("side", sa.String(10), nullable=False, server_default="other"),
    )
    op.add_column("matter_parties", sa.Column("position", sa.Integer(), nullable=True))

    op.create_table(
        "matter_advocates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("matter_id", UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("role", sa.String(24), nullable=False, server_default="arguing_counsel"),
        sa.Column("bar_enrolment_number", sa.String(60), nullable=True),
        sa.Column("firm", sa.String(200), nullable=True),
        sa.Column("party_represented", sa.String(200), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("is_lead", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_matter_advocates_tenant_id", "matter_advocates", ["tenant_id"])
    op.create_index("ix_matter_advocates_matter_id", "matter_advocates", ["matter_id"])
    op.create_index("ix_matter_advocates_side", "matter_advocates", ["side"])
    op.create_index("ix_matter_advocates_user_id", "matter_advocates", ["user_id"])

    # Tenant isolation, same predicate as every other tenant-scoped table.
    if op.get_bind().dialect.name == "postgresql":
        predicate = (
            "current_setting('app.bypass_rls', true) = 'on' "
            "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
        )
        op.execute("ALTER TABLE matter_advocates ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE matter_advocates FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON matter_advocates "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON matter_advocates")
    op.drop_table("matter_advocates")
    op.drop_column("matter_parties", "position")
    op.drop_column("matter_parties", "side")
    op.drop_index("ix_matters_next_hearing_date", table_name="matters")
    op.drop_index("ix_matters_court_level", table_name="matters")
    op.drop_index("ix_matters_cnr_number", table_name="matters")
    for column in reversed(_MATTER_COLUMNS):
        op.drop_column("matters", column.name)
