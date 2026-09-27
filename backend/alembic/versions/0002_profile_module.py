"""Professional profile module: profiles, endorsements, recommendations, verification.

Revision ID: 0002_profile
Revises: 0001_initial
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_profile"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = sa.Uuid(as_uuid=True)

TENANT_TABLES = [
    "professional_profiles",
    "profile_endorsements",
    "profile_recommendations",
    "bar_verification_requests",
]


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _tenant_col() -> sa.Column:
    return sa.Column("tenant_id", UUID, nullable=False)


def upgrade() -> None:
    op.create_table(
        "professional_profiles",
        sa.Column("id", UUID, primary_key=True),
        _tenant_col(),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("headline", sa.String(200), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("enrollment_number", sa.String(80), nullable=True),
        sa.Column("bar_council", sa.String(150), nullable=True),
        sa.Column("year_of_enrollment", sa.Integer(), nullable=True),
        sa.Column("years_of_experience", sa.Integer(), nullable=True),
        sa.Column("practice_areas", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("courts", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("languages", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("education", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("achievements", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("office_address", sa.String(400), nullable=True),
        sa.Column("website", sa.String(300), nullable=True),
        sa.Column("linkedin_url", sa.String(300), nullable=True),
        sa.Column("consultation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consultation_fee", sa.Numeric(10, 2), nullable=True),
        sa.Column("availability", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="unverified"),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="public"),
        sa.Column("avg_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="professional_profiles_user"),
    )
    op.create_index("ix_professional_profiles_tenant_id", "professional_profiles", ["tenant_id"])
    op.create_index("ix_professional_profiles_user_id", "professional_profiles", ["user_id"])

    op.create_table(
        "profile_endorsements",
        sa.Column("id", UUID, primary_key=True),
        _tenant_col(),
        sa.Column("profile_id", UUID, nullable=False),
        sa.Column("endorser_user_id", UUID, nullable=False),
        sa.Column("skill", sa.String(120), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["professional_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endorser_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("profile_id", "endorser_user_id", "skill", name="endorsement_unique"),
    )
    op.create_index("ix_profile_endorsements_tenant_id", "profile_endorsements", ["tenant_id"])
    op.create_index("ix_profile_endorsements_profile_id", "profile_endorsements", ["profile_id"])
    op.create_index("ix_profile_endorsements_endorser_user_id", "profile_endorsements", ["endorser_user_id"])

    op.create_table(
        "profile_recommendations",
        sa.Column("id", UUID, primary_key=True),
        _tenant_col(),
        sa.Column("profile_id", UUID, nullable=False),
        sa.Column("author_user_id", UUID, nullable=False),
        sa.Column("relationship_context", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["professional_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_profile_recommendations_tenant_id", "profile_recommendations", ["tenant_id"])
    op.create_index("ix_profile_recommendations_profile_id", "profile_recommendations", ["profile_id"])
    op.create_index("ix_profile_recommendations_author_user_id", "profile_recommendations", ["author_user_id"])

    op.create_table(
        "bar_verification_requests",
        sa.Column("id", UUID, primary_key=True),
        _tenant_col(),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("enrollment_number", sa.String(80), nullable=False),
        sa.Column("bar_council", sa.String(150), nullable=False),
        sa.Column("document_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewer_notes", sa.String(500), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_bar_verification_requests_tenant_id", "bar_verification_requests", ["tenant_id"])
    op.create_index("ix_bar_verification_requests_user_id", "bar_verification_requests", ["user_id"])

    _apply_rls()


def _apply_rls() -> None:
    predicate = (
        "current_setting('app.bypass_rls', true) = 'on' "
        "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("bar_verification_requests")
    op.drop_table("profile_recommendations")
    op.drop_table("profile_endorsements")
    op.drop_table("professional_profiles")
