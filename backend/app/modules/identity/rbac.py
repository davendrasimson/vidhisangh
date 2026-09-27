"""RBAC catalog: the canonical permission taxonomy and system-role definitions.

Permissions follow a ``module:action`` convention. System roles bundle them.
The seeder (``app.scripts.seed``) reads these definitions to populate the
``permissions`` and ``roles`` tables idempotently, so authorization is
data-driven and auditable rather than hard-coded in endpoints.

``WILDCARD`` ("*") grants every permission and is reserved for the platform
System Administrator.
"""

from __future__ import annotations

from typing import NamedTuple

WILDCARD = "*"


class PermissionDef(NamedTuple):
    code: str
    name: str
    module: str
    description: str


def _crud(module: str, label: str) -> list[PermissionDef]:
    """Generate the standard create/read/update/delete/manage set for a module."""
    return [
        PermissionDef(f"{module}:create", f"Create {label}", module, f"Create {label}."),
        PermissionDef(f"{module}:read", f"View {label}", module, f"View {label}."),
        PermissionDef(f"{module}:update", f"Edit {label}", module, f"Edit {label}."),
        PermissionDef(f"{module}:delete", f"Delete {label}", module, f"Delete {label}."),
        PermissionDef(f"{module}:manage", f"Manage {label}", module, f"Full control over {label}."),
    ]


# ─── Permission catalog ─────────────────────────────────────────────
PERMISSIONS: list[PermissionDef] = [
    # Administration
    *_crud("tenant", "organisation settings"),
    *_crud("user", "users"),
    *_crud("role", "roles & permissions"),
    PermissionDef("audit:read", "View audit logs", "audit", "Read the immutable audit trail."),
    PermissionDef("billing:manage", "Manage subscription", "billing", "Manage plan & billing."),
    # Professional network / profile
    *_crud("profile", "professional profiles"),
    *_crud("post", "network posts"),
    *_crud("connection", "connections"),
    # Practice management
    *_crud("matter", "matters / cases"),
    *_crud("hearing", "hearings"),
    *_crud("task", "tasks"),
    *_crud("document", "documents"),
    *_crud("client", "clients"),
    *_crud("invoice", "invoices"),
    *_crud("timeentry", "time entries"),
    *_crud("lead", "CRM leads"),
    # Research & AI
    PermissionDef("research:use", "Use legal research", "research", "Run legal research queries."),
    PermissionDef("ai:draft", "Use AI drafting", "ai", "Generate documents with AI."),
    PermissionDef("ai:assist", "Use AI assistants", "ai", "Use litigation/meeting AI assistants."),
    # Knowledge & marketplace
    *_crud("knowledge", "knowledge base"),
    *_crud("marketplace", "marketplace listings"),
    # Analytics
    PermissionDef("analytics:view", "View analytics", "analytics", "View practice analytics dashboards."),
    # Integrations
    PermissionDef("webhook:manage", "Manage webhooks", "webhook", "Register & manage outbound webhooks."),
    PermissionDef("apikey:manage", "Manage API keys", "apikey", "Create & revoke programmatic API keys."),
]

ALL_PERMISSION_CODES: list[str] = [p.code for p in PERMISSIONS]


class RoleDef(NamedTuple):
    code: str
    name: str
    description: str
    permissions: list[str]  # explicit codes, or [WILDCARD]


def _read_only(*modules: str) -> list[str]:
    return [f"{m}:read" for m in modules]


# ─── System roles ───────────────────────────────────────────────────
# Non-exhaustive but covers the primary personas; tenants add custom roles.
SYSTEM_ROLES: list[RoleDef] = [
    RoleDef("system_admin", "System Administrator", "Platform-wide superuser.", [WILDCARD]),
    RoleDef(
        "org_admin",
        "Organisation Admin",
        "Full control within the tenant.",
        [c for c in ALL_PERMISSION_CODES],
    ),
    RoleDef(
        "managing_partner",
        "Managing Partner",
        "Firm leadership: full practice + billing + people.",
        [c for c in ALL_PERMISSION_CODES if not c.startswith(("tenant:", "role:"))],
    ),
    RoleDef(
        "partner",
        "Partner",
        "Senior lawyer with broad matter and billing access.",
        [
            "matter:manage", "hearing:manage", "task:manage", "document:manage",
            "client:manage", "invoice:manage", "timeentry:manage", "lead:manage",
            "research:use", "ai:draft", "ai:assist", "knowledge:manage",
            "profile:update", "post:create", "connection:create", "analytics:view",
        ],
    ),
    RoleDef(
        "senior_associate",
        "Senior Associate",
        "Handles matters and drafting; limited financial access.",
        [
            "matter:create", "matter:read", "matter:update",
            "hearing:manage", "task:manage", "document:manage", "client:read",
            "timeentry:create", "timeentry:read", "research:use", "ai:draft",
            "ai:assist", "knowledge:create", "knowledge:read", "profile:update",
        ],
    ),
    RoleDef(
        "associate",
        "Associate",
        "Day-to-day matter execution.",
        [
            "matter:read", "matter:update", "hearing:read", "hearing:update",
            "task:manage", "document:create", "document:read", "document:update",
            "client:read", "timeentry:create", "timeentry:read",
            "research:use", "ai:draft", "knowledge:read", "profile:update",
        ],
    ),
    RoleDef(
        "junior_advocate",
        "Junior Advocate",
        "Supervised research and drafting.",
        [
            "matter:read", "hearing:read", "task:create", "task:read", "task:update",
            "document:create", "document:read", "research:use", "ai:draft",
            "knowledge:read", "profile:update",
        ],
    ),
    RoleDef(
        "legal_researcher",
        "Legal Researcher",
        "Research-focused access.",
        ["research:use", "ai:assist", "knowledge:manage", *_read_only("matter", "document"), "profile:update"],
    ),
    RoleDef(
        "accountant",
        "Accountant",
        "Billing and financials.",
        ["invoice:manage", "timeentry:read", "billing:manage", "analytics:view", *_read_only("matter", "client")],
    ),
    RoleDef(
        "clerk",
        "Clerk",
        "Filing, hearings, and document logistics.",
        ["hearing:manage", "document:create", "document:read", "task:manage", *_read_only("matter", "client")],
    ),
    RoleDef(
        "secretary",
        "Secretary",
        "Scheduling and administrative support.",
        ["task:manage", "hearing:read", "document:read", *_read_only("matter", "client"), "profile:read"],
    ),
    RoleDef(
        "receptionist",
        "Receptionist",
        "Front-office lead capture and scheduling.",
        ["lead:manage", "task:create", "task:read", *_read_only("client")],
    ),
    RoleDef(
        "corporate_counsel",
        "Corporate Counsel",
        "In-house legal for corporate tenants.",
        [
            "matter:manage", "document:manage", "task:manage", "research:use",
            "ai:draft", "ai:assist", "knowledge:manage", "invoice:read", "profile:update",
        ],
    ),
    RoleDef(
        "client",
        "Client",
        "External client portal access (own matters only — enforced via ABAC).",
        ["matter:read", "document:read", "invoice:read", "task:read"],
    ),
    RoleDef(
        "student",
        "Law Student",
        "Learning and research.",
        ["research:use", "knowledge:read", "post:create", "connection:create", "profile:update"],
    ),
    RoleDef(
        "mentor",
        "Mentor",
        "Guides students and juniors.",
        ["knowledge:manage", "post:create", "connection:create", "profile:update", "marketplace:manage"],
    ),
    RoleDef(
        "expert_witness",
        "Expert Witness",
        "Marketplace expert.",
        ["marketplace:manage", "profile:update", "post:create", "connection:create"],
    ),
    RoleDef(
        "arbitrator",
        "Arbitrator",
        "Alternative dispute resolution professional.",
        ["matter:read", "document:read", "marketplace:manage", "profile:update", "connection:create"],
    ),
    RoleDef(
        "mediator",
        "Mediator",
        "Mediation professional.",
        ["matter:read", "document:read", "marketplace:manage", "profile:update", "connection:create"],
    ),
    RoleDef(
        "guest",
        "Guest",
        "Minimal read-only access.",
        ["profile:read", "post:read"],
    ),
]

SYSTEM_ROLE_CODES: list[str] = [r.code for r in SYSTEM_ROLES]
DEFAULT_SIGNUP_ROLE = "org_admin"  # first user of a new tenant owns it
