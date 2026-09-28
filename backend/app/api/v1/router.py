"""Aggregate every module router under the versioned API prefix.

New functional modules (matters, documents, billing, research, …) register
their routers here as they are implemented — keeping a single, discoverable
composition root for the HTTP surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.ratelimit import default_rate_limit
from app.modules.analytics.router import router as analytics_router
from app.modules.apikeys.router import router as apikeys_router
from app.modules.audit.router import router as audit_router
from app.modules.billing.router import router as billing_router
from app.modules.calendar.router import router as calendar_router
from app.modules.clients.router import public_router as kyc_public_router
from app.modules.clients.router import router as clients_router
from app.modules.crm.router import router as crm_router
from app.modules.documents.router import router as documents_router
from app.modules.drafting.router import router as drafting_router
from app.modules.featureflags.router import router as featureflags_router
from app.modules.groups.router import router as groups_router
from app.modules.health.router import admin_router as system_router
from app.modules.identity.router import router as identity_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.marketplace.router import router as marketplace_router
from app.modules.matters.router import router as matters_router
from app.modules.messaging.router import router as messaging_router
from app.modules.messaging.ws import ws_router
from app.modules.network.router import router as network_router
from app.modules.news.router import router as news_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.router import router as payments_router
from app.modules.plans.router import router as plans_router
from app.modules.portal.router import router as portal_router
from app.modules.privacy.router import router as privacy_router
from app.modules.profile.router import router as profile_router
from app.modules.rates.router import router as rates_router
from app.modules.research.router import router as research_router
from app.modules.support.router import router as support_router
from app.modules.tenancy.router import router as tenancy_router
from app.modules.webhooks.router import router as webhooks_router

# Every versioned route gets the general per-IP bucket (audit A-2); routes add
# their own tighter buckets on top (credentials, MFA, uploads, public tokens).
api_router = APIRouter(dependencies=[Depends(default_rate_limit)])
api_router.include_router(identity_router)
api_router.include_router(tenancy_router)
api_router.include_router(profile_router)
api_router.include_router(network_router)
api_router.include_router(groups_router)
api_router.include_router(messaging_router)
api_router.include_router(notifications_router)
api_router.include_router(matters_router)
api_router.include_router(documents_router)
api_router.include_router(drafting_router)
api_router.include_router(clients_router)
api_router.include_router(kyc_public_router)
api_router.include_router(portal_router)
api_router.include_router(calendar_router)
api_router.include_router(research_router)
api_router.include_router(news_router)
api_router.include_router(payments_router)
api_router.include_router(crm_router)
api_router.include_router(billing_router)
api_router.include_router(rates_router)
api_router.include_router(privacy_router)
api_router.include_router(knowledge_router)
api_router.include_router(marketplace_router)
api_router.include_router(analytics_router)
api_router.include_router(featureflags_router)
api_router.include_router(plans_router)
api_router.include_router(audit_router)
api_router.include_router(system_router)
api_router.include_router(webhooks_router)
api_router.include_router(apikeys_router)
api_router.include_router(support_router)
api_router.include_router(ws_router)  # WebSocket: /api/v1/ws

# ── Roadmap: register additional module routers here ────────────────
# api_router.include_router(matter_router)
# api_router.include_router(document_router)
# api_router.include_router(billing_router)
# api_router.include_router(research_router)
