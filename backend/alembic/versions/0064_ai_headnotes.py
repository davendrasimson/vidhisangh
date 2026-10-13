"""AI-generated headnotes on judgments, stored apart from the Court's own text.

`headnote` keeps what it holds today (the Court's operative disposal for SC
reports, a registry line for HC orders). The AI headnote is original summary
writing, always shown with an "AI-generated" flag, and records which model wrote
it, when, and under which format version, so it can be regenerated or audited.

Revision ID: 0064_ai_headnotes
Revises: 0063_registration_verification
"""

import sqlalchemy as sa

from alembic import op

revision = "0064_ai_headnotes"
down_revision = "0063_registration_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("judgments", sa.Column("ai_headnote", sa.JSON(), nullable=True))
    op.add_column("judgments", sa.Column("ai_headnote_model", sa.String(80), nullable=True))
    op.add_column(
        "judgments", sa.Column("ai_headnote_generated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("judgments", sa.Column("ai_headnote_version", sa.String(20), nullable=True))


def downgrade() -> None:
    for name in ("ai_headnote_version", "ai_headnote_generated_at", "ai_headnote_model", "ai_headnote"):
        op.drop_column("judgments", name)
