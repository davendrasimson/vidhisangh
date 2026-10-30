"""Index judgments.neutral_citation for the cite check's exact lookups.

Revision ID: 0079_neutral_citation_index
Revises: 0078_whatsapp_updates

The cite check (30 Oct 2026) resolves INSC and High Court neutral citations
("2019 INSC 267", "2023:AHC:174410") by equality on ``neutral_citation``; with
no index that was a sequential scan over 5.9M rows, 10.7 s per citation on
production. ``citation`` already has its unique index (0034). Built
CONCURRENTLY so writes are not blocked while the table is scanned.
"""

from __future__ import annotations

from alembic import op

revision = "0079_neutral_citation_index"
down_revision = "0078_whatsapp_updates"
branch_labels = None
depends_on = None

_INDEX = "ix_judgments_neutral_citation"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} ON judgments (neutral_citation)")
    else:
        op.create_index(_INDEX, "judgments", ["neutral_citation"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
    else:
        op.drop_index(_INDEX, table_name="judgments")
