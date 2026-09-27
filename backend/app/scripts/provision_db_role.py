"""Provision the least-privilege PostgreSQL application role (go-live hardening).

PostgreSQL **skips Row-Level Security entirely** for superusers and for roles
with the ``BYPASSRLS`` attribute. Local dev connects as ``postgres`` (a
superuser), so the ``tenant_isolation`` policies on every tenant-scoped table are
silently ignored and DB-level tenant isolation is effectively **off** — only the
application-level ``tenant_id`` filtering in the repositories remains.

Before deploying to any shared / non-local environment you MUST connect the
application as a dedicated role that is ``NOSUPERUSER`` and ``NOBYPASSRLS`` and
holds only the DML privileges it needs. This script provisions exactly that role.

Run it as a Postgres admin/superuser (it only needs to run once per environment,
and is safe to re-run — it is idempotent)::

    # from backend/ , with the admin connection in VS_POSTGRES_* (or via flags):
    python -m app.scripts.provision_db_role --role vidhisangh_app \\
        --password "$VS_APP_DB_PASSWORD"

Then point the application at the new role and keep an admin/owner role for
migrations (the app role has no DDL rights, so it cannot run Alembic)::

    VS_POSTGRES_USER=vidhisangh_app
    VS_POSTGRES_PASSWORD=...            # the password you passed above

Migrations continue to run as the owning/admin role; ``--migrator`` records that
role so ``ALTER DEFAULT PRIVILEGES`` keeps the app role's grants current as new
tables land in future migrations.

Use ``--dry-run`` to print the exact SQL without connecting.
"""

from __future__ import annotations

import argparse
import re
import sys

import psycopg
from psycopg import sql

from app.core.config import settings

# A role/schema/database name is a bare SQL identifier. We validate before ever
# interpolating one into a statement so the grant strings (shared with the test
# suite) can be plain, driver-agnostic SQL rather than driver-specific objects.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The application only ever performs DML on tenant data — never DDL, TRUNCATE,
# or ownership operations. This is the whole point of the least-privilege role.
_TABLE_PRIVS = "SELECT, INSERT, UPDATE, DELETE"
_SEQUENCE_PRIVS = "USAGE, SELECT"

# Attributes that make RLS actually apply to this role. NOBYPASSRLS is the one
# that matters for isolation; the rest keep the blast radius small.
_ROLE_ATTRIBUTES = "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT"


def _ident(name: str) -> str:
    """Validate and double-quote a SQL identifier (role/database/schema name)."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return '"' + name + '"'


def grant_statements(
    role: str,
    database: str,
    *,
    migrator: str | None = None,
    schema: str = "public",
) -> list[str]:
    """The exact privilege grants the application role receives.

    Least privilege: CONNECT to the database, USAGE on the schema, DML on all
    existing tables and sequences, and — when ``migrator`` is given — default
    privileges so tables/sequences created by future migrations (run as the
    ``migrator`` role) are covered automatically without re-running this script.

    Returned as plain SQL strings (identifiers pre-validated and quoted) so the
    RLS integration test can apply the *same* grants to its throwaway probe role.
    """
    r, sch = _ident(role), _ident(schema)
    stmts = [
        f"GRANT CONNECT ON DATABASE {_ident(database)} TO {r}",
        f"GRANT USAGE ON SCHEMA {sch} TO {r}",
        f"GRANT {_TABLE_PRIVS} ON ALL TABLES IN SCHEMA {sch} TO {r}",
        f"GRANT {_SEQUENCE_PRIVS} ON ALL SEQUENCES IN SCHEMA {sch} TO {r}",
    ]
    if migrator:
        m = _ident(migrator)
        stmts += [
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {m} IN SCHEMA {sch} "
            f"GRANT {_TABLE_PRIVS} ON TABLES TO {r}",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {m} IN SCHEMA {sch} "
            f"GRANT {_SEQUENCE_PRIVS} ON SEQUENCES TO {r}",
        ]
    return stmts


def _role_ddl(role: str, *, exists: bool, login: bool, password: str | None) -> sql.Composed:
    """CREATE-or-ALTER the role with least-privilege attributes.

    Password is bound as a SQL literal (DDL can't take query parameters) via
    psycopg's composition, so it is safely quoted and never string-formatted.
    """
    return sql.SQL("{verb} ROLE {role} WITH {login} {attrs} PASSWORD {pw}").format(
        verb=sql.SQL("ALTER" if exists else "CREATE"),
        role=sql.Identifier(role),
        login=sql.SQL("LOGIN" if login else "NOLOGIN"),
        attrs=sql.SQL(_ROLE_ATTRIBUTES),
        pw=sql.Literal(password) if password is not None else sql.SQL("NULL"),
    )


def provision(
    conn: psycopg.Connection,
    *,
    role: str,
    password: str | None,
    database: str,
    migrator: str | None,
    login: bool = True,
    schema: str = "public",
) -> list[str]:
    """Create/update the role and apply its grants on an open admin connection.

    Returns the list of statements executed (for logging/inspection). Commits on
    success.
    """
    _ident(role)  # fail fast on an unsafe name before touching the database
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        exists = cur.fetchone() is not None
        ddl = _role_ddl(role, exists=exists, login=login, password=password)
        cur.execute(ddl)
        executed = [ddl.as_string(conn)]
        for stmt in grant_statements(role, database, migrator=migrator, schema=schema):
            cur.execute(stmt)
            executed.append(stmt)
    conn.commit()
    return executed


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m app.scripts.provision_db_role",
        description="Provision the least-privilege PostgreSQL application role.",
    )
    p.add_argument("--role", required=True, help="Name of the application role to create/update.")
    p.add_argument(
        "--password",
        default=None,
        help="Password for the (LOGIN) role. Required unless --no-login.",
    )
    p.add_argument(
        "--no-login",
        dest="login",
        action="store_false",
        help="Provision a NOLOGIN role (e.g. a group role).",
    )
    p.add_argument("--database", default=settings.POSTGRES_DB, help="Target database.")
    p.add_argument("--schema", default="public", help="Schema to grant on (default: public).")
    p.add_argument(
        "--migrator",
        default=None,
        help="Role that owns/creates tables in migrations (defaults to --admin-user). "
        "Used for ALTER DEFAULT PRIVILEGES so future tables stay granted.",
    )
    # Admin connection used to run the provisioning. Defaults to VS_POSTGRES_*,
    # which in the provisioning scenario should point at an admin/superuser.
    p.add_argument("--admin-user", default=settings.POSTGRES_USER)
    p.add_argument("--admin-password", default=settings.POSTGRES_PASSWORD)
    p.add_argument("--admin-host", default=settings.POSTGRES_HOST)
    p.add_argument("--admin-port", type=int, default=settings.POSTGRES_PORT)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the SQL that would run, without connecting.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.login and not args.password:
        print("error: --password is required for a LOGIN role (or pass --no-login)", file=sys.stderr)
        return 2

    migrator = args.migrator or args.admin_user

    if args.dry_run:
        # Show role DDL (with the password masked) plus the grants.
        _ident(args.role)
        masked = _role_ddl(args.role, exists=False, login=args.login, password="********")
        print("-- role:")
        # as_string needs a connection for quoting; render manually for dry-run.
        print(f"CREATE ROLE {_ident(args.role)} WITH "
              f"{'LOGIN' if args.login else 'NOLOGIN'} {_ROLE_ATTRIBUTES} PASSWORD '********';")
        print("-- grants:")
        for stmt in grant_statements(args.role, args.database, migrator=migrator, schema=args.schema):
            print(stmt + ";")
        return 0

    with psycopg.connect(
        host=args.admin_host,
        port=args.admin_port,
        dbname=args.database,
        user=args.admin_user,
        password=args.admin_password,
        autocommit=False,
    ) as conn:
        provision(
            conn,
            role=args.role,
            password=args.password,
            database=args.database,
            migrator=migrator,
            login=args.login,
            schema=args.schema,
        )
    print(f"Provisioned least-privilege role {args.role!r} on database {args.database!r} "
          f"(NOSUPERUSER, NOBYPASSRLS). Point VS_POSTGRES_USER/PASSWORD at it for the app.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
