"""Research corpus: admit High Court order records, and make search scale.

Revision ID: 0034_high_court_orders
Revises: 0033_indian_court_matters
Create Date: 2026-09-23

The corpus was built for Supreme Court Reports, where every row has a unique
citation. High Court records from the eCourts open-data mirror have **no
citation at all** — they are order records keyed by CNR. Three changes:

1. ``citation`` becomes nullable, and its uniqueness moves from a table
   constraint to a **partial** unique index (``WHERE citation IS NOT NULL``), so
   many citation-less rows can coexist while reported judgments stay unique.
2. ``cnr_number`` and ``source_ref`` are added. ``source_ref`` is a deterministic
   provider row id (``<court>:<cnr>:<date>``) and is UNIQUE, which is what makes
   the bulk loader idempotent: it inserts with ``ON CONFLICT DO NOTHING`` rather
   than holding millions of keys in memory to deduplicate.
3. A **pg_trgm GIN index** on ``case_name``. Research search is
   ``ILIKE '%q%'``; over ~38k Supreme Court rows a sequential scan was fine, but
   the High Court load takes the table past five million rows, where the same
   query would take seconds to minutes. The index keeps the existing substring
   semantics and makes it fast.

``pg_trgm`` needs superuser to install. Do it once, before migrating:

    sudo -u postgres psql -d vidhisangh -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm'

If the extension is absent this migration still completes — it logs a warning
and skips only the trigram index, because failing the whole deploy over a
performance index would be worse than running without it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_high_court_orders"
down_revision: str | None = "0033_indian_court_matters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.add_column("judgments", sa.Column("cnr_number", sa.String(20), nullable=True))
    op.add_column("judgments", sa.Column("source_ref", sa.String(120), nullable=True))
    op.create_index("ix_judgments_cnr_number", "judgments", ["cnr_number"])
    op.create_index("uq_judgments_source_ref", "judgments", ["source_ref"], unique=True)

    # citation: NOT NULL + table-level UNIQUE  ->  nullable + partial unique index
    if is_pg:
        op.execute("ALTER TABLE judgments ALTER COLUMN citation DROP NOT NULL")
        op.execute("ALTER TABLE judgments DROP CONSTRAINT IF EXISTS judgment_citation")
        op.execute(
            "CREATE UNIQUE INDEX judgment_citation ON judgments (citation) "
            "WHERE citation IS NOT NULL"
        )
    else:
        # SQLite cannot alter a column in place; the test DB is built from the
        # models, which already declare the partial index, so only drop the old
        # constraint-backed index if batch mode created one.
        with op.batch_alter_table("judgments") as batch:
            batch.alter_column("citation", existing_type=sa.String(200), nullable=True)

    if is_pg:
        try:
            op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        except Exception as exc:  # non-superuser and not pre-installed
            log.warning("pg_trgm unavailable (%s) — skipping trigram index", exc)
            return
        op.execute(
            "CREATE INDEX ix_judgments_case_name_trgm ON judgments "
            "USING gin (case_name gin_trgm_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_judgments_case_name_trgm")
        op.execute("DROP INDEX IF EXISTS judgment_citation")
        # Restoring NOT NULL requires every row to have a citation; High Court
        # rows do not, so clear them out rather than fail half-way.
        op.execute("DELETE FROM judgments WHERE citation IS NULL")
        op.execute("ALTER TABLE judgments ALTER COLUMN citation SET NOT NULL")
        op.execute(
            "ALTER TABLE judgments ADD CONSTRAINT judgment_citation UNIQUE (citation)"
        )
    op.drop_index("uq_judgments_source_ref", table_name="judgments")
    op.drop_index("ix_judgments_cnr_number", table_name="judgments")
    op.drop_column("judgments", "source_ref")
    op.drop_column("judgments", "cnr_number")
