"""Every datetime column must be mapped ``DateTime(timezone=True)``.

The services write ``datetime.now(UTC)``. A bare ``Mapped[datetime]`` maps to
TIMESTAMP WITHOUT TIME ZONE, and asyncpg rejects an aware value for it ("can't
subtract offset-naive and offset-aware datetimes") — on Postgres only, so the
SQLite suite never sees it. Sending a message failed this way in production.
"""
from sqlalchemy import DateTime

import app.db.base  # noqa: F401  (registers every model)
from app.db.base_class import Base


def test_every_datetime_column_is_timezone_aware():
    naive = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime) and not column.type.timezone
    ]
    assert naive == []
