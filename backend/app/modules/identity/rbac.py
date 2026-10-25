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
    # Professional network / profile / community
    *_crud("profile", "professional profiles"),
    *_crud("post", "network posts"),
    *_crud("connection", "connections"),
    *_crud("group", "groups & communities"),
    PermissionDef("message:read", "Read messages", "message", "Read conversations you take part in."),
    PermissionDef("message:send", "Send messages", "message", "Start conversations and send messages."),
    PermissionDef("notification:read", "Read notifications", "notification", "Read and manage your own notifications."),
    # Practice management
    *_crud("matter", "matters / cases"),
    *_crud("hearing", "hearings"),
    *_crud("task", "tasks"),
    *_crud("document", "documents"),
    *_crud("client", "clients"),
    *_crud("invoice", "invoices"),
    *_crud("timeentry", "time entries"),
    *_crud("lead", "CRM leads"),
    PermissionDef("calendar:read", "View calendar", "calendar", "View the organisation calendar and agenda."),
    PermissionDef("calendar:manage", "Manage calendar", "calendar", "Create, edit and delete calendar events."),
    # Research, news & AI
    PermissionDef("research:use", "Use legal research", "research", "Run legal research queries."),
    PermissionDef(
        "research:curate", "Curate the judgment corpus", "research",
        "Add or edit judgments and citations in the shared research library (platform staff / firm leadership).",
    ),
    PermissionDef(
        "news:curate", "Curate legal news", "news",
        "Add or remove items in the shared legal news feed (platform staff / firm leadership).",
    ),
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


# ─── Role groups ────────────────────────────────────────────────────
# Codes every *internal* (firm-staff) role receives on top of its practice
# permissions: read the organisation, take part in the network, groups,
# messaging, calendar and notifications.
_INTERNAL_COMMON: list[str] = [
    "tenant:read",
    "profile:read",
    "post:read", "post:create", "post:update", "post:delete",
    "connection:read", "connection:create",
    "group:read", "group:create", "group:update",
    "message:read", "message:send",
    "calendar:read",
    "notification:read",
]

# Codes for roles that only *consume* the network (no matter/document access):
# read the network + directory, connect, message, be notified.
_NETWORK_PARTICIPANT: list[str] = [
    "profile:read", "post:read", "connection:read", "connection:create",
    "group:read", "message:read", "message:send", "notification:read",
]

# Roles held by people *outside* the firm (clients, neutrals). They never see
# practice-management data through the main API — clients use the portal, and
# arbitrators/mediators receive material through messaging/documents shared
# with them explicitly. Kept as a set so services can apply extra scoping.
EXTERNAL_ROLES: frozenset[str] = frozenset({"client", "arbitrator", "mediator"})

# Curation of the *shared, cross-tenant* corpus and news feed is restricted to
# platform staff and firm leadership — never students, associates or clients.
_CURATORS: list[str] = ["research:curate", "news:curate"]


# ─── System roles ───────────────────────────────────────────────────
# Non-exhaustive but covers the primary personas; tenants add custom roles.
# ``expand_permissions`` (below) adds the create/read/update/delete codes for
# every ``X:manage`` a role holds, so a partner with ``matter:manage`` can list
# matters (the guard checks the exact ``matter:read`` code).
_SYSTEM_ROLES: list[RoleDef] = [
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
        "Firm leadership: full practice + billing + people. May curate the shared corpus and news.",
        [c for c in ALL_PERMISSION_CODES if not c.startswith(("tenant:", "role:"))] + ["tenant:read"],
    ),
    RoleDef(
        "partner",
        "Partner",
        "Senior lawyer with broad matter and billing access.",
        [
            "matter:manage", "hearing:manage", "task:manage", "document:manage",
            "client:manage", "invoice:manage", "timeentry:manage", "lead:manage",
            "research:use", "ai:draft", "ai:assist", "knowledge:manage",
            "profile:update", "analytics:view", "calendar:manage",
            *_INTERNAL_COMMON,
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
            "calendar:manage", *_INTERNAL_COMMON,
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
            "calendar:manage", *_INTERNAL_COMMON,
        ],
    ),
    RoleDef(
        "junior_advocate",
        "Junior Advocate",
        "Supervised research and drafting.",
        [
            "matter:read", "hearing:read", "task:create", "task:read", "task:update",
            "document:create", "document:read", "research:use", "ai:draft",
            "timeentry:create", "timeentry:read", "knowledge:read", "profile:update",
            "calendar:manage", *_INTERNAL_COMMON,
        ],
    ),
    RoleDef(
        "legal_researcher",
        "Legal Researcher",
        "Research-focused access.",
        [
            "research:use", "ai:assist", "knowledge:manage", *_read_only("matter", "document"),
            "profile:update", *_INTERNAL_COMMON,
        ],
    ),
    RoleDef(
        "accountant",
        "Accountant",
        "Billing and financials.",
        [
            "invoice:manage", "timeentry:read", "billing:manage", "analytics:view",
            *_read_only("matter", "client"), *_INTERNAL_COMMON,
        ],
    ),
    RoleDef(
        "clerk",
        "Clerk",
        "Filing, hearings, and document logistics.",
        [
            "hearing:manage", "document:create", "document:read", "task:manage",
            *_read_only("matter", "client"), "calendar:manage", *_INTERNAL_COMMON,
        ],
    ),
    RoleDef(
        "secretary",
        "Secretary",
        "Scheduling and administrative support.",
        [
            "task:manage", "hearing:read", "document:read", *_read_only("matter", "client"),
            "calendar:manage", *_INTERNAL_COMMON,
        ],
    ),
    RoleDef(
        "receptionist",
        "Receptionist",
        "Front-office lead capture and scheduling.",
        ["lead:manage", "task:create", "task:read", *_read_only("client"), "calendar:manage", *_INTERNAL_COMMON],
    ),
    RoleDef(
        "corporate_counsel",
        "Corporate Counsel",
        "In-house legal for corporate tenants.",
        [
            "matter:manage", "document:manage", "task:manage", "research:use",
            "ai:draft", "ai:assist", "knowledge:manage", "invoice:read",
            "timeentry:create", "timeentry:read", "profile:update",
            "calendar:manage", *_INTERNAL_COMMON,
        ],
    ),
    RoleDef(
        "client",
        "Client",
        "External client. Sees their own matters, documents and invoices through the "
        "client portal only — this role grants NO firm-wide practice data access "
        "(matter/document/invoice/task read were removed in the Sept 2026 audit, A-6).",
        ["message:read", "message:send", "notification:read"],
    ),
    RoleDef(
        "student",
        "Law Student",
        "Learning and research.",
        ["research:use", "knowledge:read", "profile:update", *_INTERNAL_COMMON],
    ),
    RoleDef(
        "mentor",
        "Mentor",
        "Guides students and juniors.",
        ["knowledge:manage", "profile:update", "marketplace:manage", *_INTERNAL_COMMON],
    ),
    RoleDef(
        "expert_witness",
        "Expert Witness",
        "Marketplace expert.",
        ["marketplace:manage", "profile:update", "post:create", *_NETWORK_PARTICIPANT],
    ),
    RoleDef(
        "arbitrator",
        "Arbitrator",
        "External alternative-dispute-resolution professional. Takes part in the network and "
        "marketplace; has no access to a firm's matters or documents (removed Sept 2026, A-6).",
        ["marketplace:manage", "profile:update", *_NETWORK_PARTICIPANT],
    ),
    RoleDef(
        "mediator",
        "Mediator",
        "External mediation professional. Takes part in the network and marketplace; has no "
        "access to a firm's matters or documents (removed Sept 2026, A-6).",
        ["marketplace:manage", "profile:update", *_NETWORK_PARTICIPANT],
    ),
    RoleDef(
        "guest",
        "Guest",
        "Minimal read-only access.",
        ["tenant:read", "profile:read", "post:read", "connection:read", "group:read",
         "message:read", "notification:read"],
    ),
]

_CRUD_ACTIONS = ("create", "read", "update", "delete")
_CATALOG_CODES = frozenset(ALL_PERMISSION_CODES)


def expand_permissions(codes: list[str]) -> list[str]:
    """``X:manage`` implies ``X:create/read/update/delete`` (when those codes
    exist in the catalog). Deduplicates while preserving order. Guards check the
    exact code, so the implication is materialised here — at seed time — rather
    than in ``CurrentUser.has_permission``."""
    if codes == [WILDCARD]:
        return list(codes)
    out: list[str] = list(dict.fromkeys(codes))
    for code in codes:
        module, _, action = code.partition(":")
        if action != "manage":
            continue
        for crud in _CRUD_ACTIONS:
            implied = f"{module}:{crud}"
            if implied in _CATALOG_CODES and implied not in out:
                out.append(implied)
    return out


def _with_curation(role: RoleDef) -> RoleDef:
    if role.code in ("managing_partner",):
        return role._replace(permissions=[*role.permissions, *_CURATORS])
    return role


SYSTEM_ROLES: list[RoleDef] = [
    r._replace(permissions=expand_permissions(r.permissions)) for r in map(_with_curation, _SYSTEM_ROLES)
]

SYSTEM_ROLE_CODES: list[str] = [r.code for r in SYSTEM_ROLES]
DEFAULT_SIGNUP_ROLE = "org_admin"  # first user of a new tenant owns it


# ─── Profession mask ────────────────────────────────────────────────
# A sitting judicial officer has no clients, fees or work to solicit, so
# whatever roles they hold, these codes are taken out of their access token
# (and API keys). It is a mask on top of RBAC, not a role, so it cannot be
# undone by an org_admin granting themselves a custom role. Keyed on the
# profile's ``professional_role``; retired judicial officers are not masked.
JUDICIAL_PROFESSIONAL_ROLES: frozenset[str] = frozenset({"judicial_officer"})
_JUDICIAL_BLOCKED_MODULES = ("client", "invoice", "timeentry", "lead", "marketplace")
JUDICIAL_BLOCKED: frozenset[str] = frozenset(
    c for c in ALL_PERMISSION_CODES if c.partition(":")[0] in _JUDICIAL_BLOCKED_MODULES
) | {"analytics:view"}


def is_judicial(professional_role: str | None) -> bool:
    return professional_role in JUDICIAL_PROFESSIONAL_ROLES


def mask_for_profession(codes: set[str], professional_role: str | None) -> set[str]:
    """The codes a user may actually use given their profession. The platform
    wildcard is left alone (platform staff)."""
    if WILDCARD in codes or not is_judicial(professional_role):
        return codes
    return codes - JUDICIAL_BLOCKED
