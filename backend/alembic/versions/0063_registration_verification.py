"""Verified email registration and mobile/WhatsApp authentication.

Revision ID: 0063_registration_verification
Revises: 0062_registration_alerts
"""

import sqlalchemy as sa

from alembic import op

revision = "0063_registration_verification"
down_revision = "0062_registration_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)
    for name in ("is_phone_verified", "verification_required"):
        # Existing users keep access; new self-registrations explicitly require verification.
        op.add_column(
            "users", sa.Column(name, sa.Boolean(), server_default=sa.false(), nullable=False)
        )
    op.add_column("users", sa.Column("email_verification_delivery_token", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verification_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_users_email_verification_next_attempt_at",
        "users",
        ["email_verification_next_attempt_at"],
    )
    op.create_index(
        "users_verified_phone_unique",
        "users",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND is_phone_verified = true"),
    )
    op.create_table(
        "phone_otp_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
    )
    op.create_index("ix_phone_otp_challenges_deleted_at", "phone_otp_challenges", ["deleted_at"])

    op.create_index("ix_phone_otp_challenges_expires_at", "phone_otp_challenges", ["expires_at"])


def downgrade() -> None:
    # Refuse to discard mobile-only accounts by restoring NOT NULL prematurely.
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
    op.drop_table("phone_otp_challenges")
    op.drop_index("users_verified_phone_unique", table_name="users")
    op.drop_index("ix_users_email_verification_next_attempt_at", table_name="users")
    for name in (
        "is_phone_verified",
        "verification_required",
        "email_verification_delivery_token",
        "email_verification_attempts",
        "email_verification_next_attempt_at",
    ):
        op.drop_column("users", name)
