"""Model registry — imports every ORM model so Alembic autogenerate and
``Base.metadata`` see the complete schema. Import this module (not individual
model modules) wherever the full metadata is required.
"""

from __future__ import annotations

# ruff: noqa: F401  (re-exports for metadata discovery)
from app.db.base_class import Base
from app.modules.apikeys.models import ApiKey
from app.modules.audit.models import AuditEvent
from app.modules.billing.models import Invoice, InvoiceLineItem
from app.modules.calendar.models import CalendarEvent
from app.modules.crm.models import Lead, LeadActivity
from app.modules.documents.models import (
    Document,
    DocumentFolder,
    DocumentVersion,
)
from app.modules.drafting.models import Draft, DraftVersion
from app.modules.clients.models import Client, ClientKycRequest
from app.modules.featureflags.models import FeatureFlag
from app.modules.groups.models import (
    Group,
    GroupMembership,
    GroupPost,
    GroupPostComment,
    GroupPostLike,
)
from app.modules.identity.models import (
    MfaBackupCode,
    OAuthState,
    Permission,
    RefreshToken,
    Role,
    TrustedDevice,
    User,
    WebAuthnChallenge,
    WebAuthnCredential,
    role_permissions,
    user_roles,
)
from app.modules.knowledge.models import KnowledgeItem
from app.modules.marketplace.models import Listing, ListingResponse
from app.modules.matters.models import (
    Hearing,
    Matter,
    MatterAdvocate,
    MatterAuthority,
    MatterFeeArrangement,
    MatterFeeEvent,
    MatterFeeMilestone,
    MatterNote,
    MatterParty,
    MatterTask,
    MatterTeamMember,
)
from app.modules.rates.models import CounselRate
from app.modules.messaging.models import (
    Conversation,
    ConversationParticipant,
    Message,
)
from app.modules.network.models import (
    Comment,
    Connection,
    Follow,
    NetworkIdentity,
    Post,
    PostBookmark,
    PostMention,
    PostReaction,
)
from app.modules.news.models import NewsItem
from app.modules.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationPreference,
)
from app.modules.payments.models import Payment
from app.modules.portal.models import (
    PortalAccess,
    PortalApproval,
    PortalDocument,
    PortalUpdate,
)
from app.modules.research.models import CaseCitation, Judgment
from app.modules.profile.models import (
    BarVerificationRequest,
    Endorsement,
    ProfessionalProfile,
    Recommendation,
)
from app.modules.tenancy.models import Tenant
from app.modules.webhooks.models import WebhookDelivery, WebhookEndpoint

__all__ = [
    "Base",
    "Tenant",
    "User",
    "Role",
    "Permission",
    "RefreshToken",
    "MfaBackupCode",
    "TrustedDevice",
    "OAuthState",
    "WebAuthnCredential",
    "WebAuthnChallenge",
    "ProfessionalProfile",
    "Endorsement",
    "Recommendation",
    "BarVerificationRequest",
    "NetworkIdentity",
    "Connection",
    "Follow",
    "Post",
    "PostReaction",
    "Comment",
    "PostBookmark",
    "PostMention",
    "Group",
    "GroupMembership",
    "GroupPost",
    "GroupPostLike",
    "GroupPostComment",
    "Conversation",
    "ConversationParticipant",
    "Message",
    "Notification",
    "NotificationPreference",
    "NotificationDelivery",
    "Matter",
    "MatterAdvocate",
    "MatterAuthority",
    "MatterParty",
    "Hearing",
    "MatterTask",
    "MatterNote",
    "MatterTeamMember",
    "MatterFeeArrangement",
    "MatterFeeMilestone",
    "MatterFeeEvent",
    "CounselRate",
    "DocumentFolder",
    "Document",
    "DocumentVersion",
    "Draft",
    "DraftVersion",
    "Client",
    "ClientKycRequest",
    "PortalAccess",
    "PortalUpdate",
    "PortalApproval",
    "PortalDocument",
    "CalendarEvent",
    "Judgment",
    "CaseCitation",
    "NewsItem",
    "Payment",
    "Lead",
    "LeadActivity",
    "Invoice",
    "InvoiceLineItem",
    "KnowledgeItem",
    "Listing",
    "ListingResponse",
    "FeatureFlag",
    "AuditEvent",
    "WebhookEndpoint",
    "WebhookDelivery",
    "ApiKey",
    "role_permissions",
    "user_roles",
]
