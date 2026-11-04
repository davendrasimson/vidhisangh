"""VidhiSangh Daily: brief sends/opens and quiz answers."""

import sqlalchemy as sa

from alembic import op

revision = "0089_daily_brief"
down_revision = "0088_sc_daily_orders"
branch_labels = None
depends_on = None


def audit_columns():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    ]


def upgrade():
    op.create_table(
        "daily_brief_sends",
        *audit_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("lead", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("detail", sa.String(200)),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("opened_via", sa.String(20)),
        sa.UniqueConstraint("user_id", "for_date", name="uq_daily_brief_user_day"),
    )
    op.create_index("ix_daily_brief_sends_user_id", "daily_brief_sends", ["user_id"])
    op.create_index("ix_daily_brief_sends_for_date", "daily_brief_sends", ["for_date"])

    op.create_table(
        "daily_quiz_answers",
        *audit_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("quiz_id", sa.String(10), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("chosen", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("user_id", "quiz_id", name="uq_daily_quiz_user_question"),
    )
    op.create_index("ix_daily_quiz_answers_user_id", "daily_quiz_answers", ["user_id"])
    op.create_index("ix_daily_quiz_answers_quiz_id", "daily_quiz_answers", ["quiz_id"])


def downgrade():
    op.drop_table("daily_quiz_answers")
    op.drop_table("daily_brief_sends")
