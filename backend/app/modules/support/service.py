"""Support and platform-operator workflows."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.channels import ChannelMessage, get_channels
from app.core.config import settings
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.core.revocation import mark_user_revoked
from app.modules.apikeys.repository import ApiKeyRepository
from app.modules.billing.models import Invoice
from app.modules.identity.models import User
from app.modules.identity.repository import RefreshTokenRepository
from app.modules.matters.models import Matter
from app.modules.network.models import Comment, Connection, NetworkIdentity, Post
from app.modules.notifications.models import NotificationChannel, NotificationType
from app.modules.notifications.service import create_notification
from app.modules.support.models import (
    PlatformAdminAction,
    SupportTicket,
    SupportTicketMessage,
    TicketStatus,
)
from app.modules.support.schemas import (
    AccountStatusRequest,
    PlatformOverview,
    PlatformPostRead,
    PlatformTenantRead,
    PlatformUserDetail,
    PlatformUserRead,
    TenantStatusRequest,
    TicketAdminUpdate,
    TicketCreate,
)
from app.modules.tenancy.models import Tenant, TenantStatus

logger = logging.getLogger("vidhisangh.support")


def require_platform_admin(is_superuser: bool) -> None:
    if not is_superuser:
        raise PermissionDeniedError("Platform administrator access is required.")


class SupportService:
    def __init__(self, session: AsyncSession, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.user_id = user_id
        self.tenant_id = tenant_id

    async def create(self, data: TicketCreate, *, name: str, email: str | None) -> SupportTicket:
        ticket = SupportTicket(
            tenant_id=self.tenant_id,
            ticket_number=f"VS-{datetime.now(UTC):%Y%m}-{secrets.token_hex(3).upper()}",
            requester_id=self.user_id,
            requester_name=name,
            requester_email=email or "",
            subject=data.subject,
            description=data.description,
            category=data.category,
            priority=data.priority,
            page_url=data.page_url,
            browser_context=data.browser_context,
        )
        self.session.add(ticket)
        await self.session.flush()
        email_provider = get_channels().provider_for(NotificationChannel.EMAIL)
        if email_provider is not None:
            try:
                await email_provider.send(
                    ChannelMessage(
                        to_email=settings.GRIEVANCE_OFFICER_EMAIL,
                        to_name="VidhiSangh Grievance Cell",
                        subject=f"{ticket.ticket_number}: {ticket.subject}",
                        body=(
                            f"{name} ({email}) submitted a {ticket.priority} priority "
                            f"{ticket.category} request.\n\n{ticket.description}"
                        ),
                        link="https://admin.vidhisangh.com/platform-admin",
                    )
                )
            except Exception as exc:
                logger.warning("support ticket alert failed: %s", type(exc).__name__)
        return await self._get(ticket.id)

    async def report_post(
        self, post: Post, *, name: str, email: str | None, category: str, reason: str
    ) -> SupportTicket:
        duplicate = await self.session.scalar(
            select(SupportTicket).where(
                SupportTicket.requester_id == self.user_id,
                SupportTicket.reported_post_id == post.id,
                SupportTicket.status != TicketStatus.CLOSED,
                SupportTicket.deleted_at.is_(None),
            )
        )
        if duplicate is not None:
            raise ValidationError(
                f"This post is already under review in grievance {duplicate.ticket_number}."
            )
        ticket = SupportTicket(
            tenant_id=self.tenant_id,
            ticket_number=f"VS-{datetime.now(UTC):%Y%m}-{secrets.token_hex(3).upper()}",
            requester_id=self.user_id,
            requester_name=name,
            requester_email=email or "",
            subject=f"Reported network post by {post.author_name}",
            description=f"Reason: {category.replace('_', ' ').title()}\n\n{reason}",
            category="post_report",
            priority="high",
            page_url=f"https://vidhisangh.com/app/network?post={post.id}",
            reported_post_id=post.id,
            reported_user_id=post.author_id,
            report_context={
                "author_name": post.author_name,
                "title": post.title,
                "content": post.content,
                "visibility": str(post.visibility),
                "created_at": post.created_at.isoformat(),
                "report_category": category,
            },
        )
        self.session.add(ticket)
        await self.session.flush()
        return await self._get(ticket.id)

    async def _get(self, ticket_id: uuid.UUID) -> SupportTicket:
        ticket = await self.session.scalar(
            select(SupportTicket)
            .where(
                SupportTicket.id == ticket_id,
                SupportTicket.tenant_id == self.tenant_id,
                SupportTicket.requester_id == self.user_id,
                SupportTicket.deleted_at.is_(None),
            )
            .options(selectinload(SupportTicket.messages))
        )
        if ticket is None:
            raise NotFoundError("Support ticket not found.")
        return ticket

    async def list_mine(self) -> list[SupportTicket]:
        result = await self.session.execute(
            select(SupportTicket)
            .where(
                SupportTicket.tenant_id == self.tenant_id,
                SupportTicket.requester_id == self.user_id,
                SupportTicket.deleted_at.is_(None),
            )
            .options(selectinload(SupportTicket.messages))
            .order_by(SupportTicket.updated_at.desc())
        )
        return list(result.scalars().all())

    async def add_message(self, ticket_id: uuid.UUID, body: str, *, name: str) -> SupportTicket:
        ticket = await self._get(ticket_id)
        self.session.add(
            SupportTicketMessage(
                tenant_id=self.tenant_id,
                ticket_id=ticket.id,
                author_id=self.user_id,
                author_name=name,
                is_staff=False,
                body=body,
            )
        )
        if ticket.status == TicketStatus.CLOSED:
            ticket.status = TicketStatus.REOPENED
            ticket.closed_at = None
        elif ticket.status == TicketStatus.WAITING_ON_USER:
            ticket.status = TicketStatus.IN_PROGRESS
        await self.session.flush()
        return await self._get(ticket.id)


class PlatformAdminService:
    def __init__(self, session: AsyncSession, actor_id: uuid.UUID, actor_email: str) -> None:
        self.session = session
        self.actor_id = actor_id
        self.actor_email = actor_email

    def _audit(
        self,
        action: str,
        entity_type: str,
        entity_id: object,
        reason: str | None,
        detail: dict | None = None,
    ) -> None:
        self.session.add(
            PlatformAdminAction(
                actor_id=self.actor_id,
                actor_email=self.actor_email,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id),
                reason=reason,
                detail=detail,
            )
        )

    async def overview(self) -> PlatformOverview:
        now = datetime.now(UTC)
        value = self.session.scalar
        users_total = int(
            await value(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
            or 0
        )
        users_active = int(
            await value(
                select(func.count())
                .select_from(User)
                .where(User.deleted_at.is_(None), User.is_active.is_(True))
            )
            or 0
        )
        tenants_total = int(
            await value(select(func.count()).select_from(Tenant).where(Tenant.deleted_at.is_(None)))
            or 0
        )
        posts_total = int(await value(select(func.count()).select_from(Post)) or 0)
        return PlatformOverview(
            users_total=users_total,
            users_active=users_active,
            users_blocked=users_total - users_active,
            users_new_30d=int(
                await value(
                    select(func.count())
                    .select_from(User)
                    .where(User.deleted_at.is_(None), User.created_at >= now - timedelta(days=30))
                )
                or 0
            ),
            tenants_total=tenants_total,
            tenants_active=int(
                await value(
                    select(func.count())
                    .select_from(Tenant)
                    .where(
                        Tenant.deleted_at.is_(None),
                        Tenant.status.in_((TenantStatus.ACTIVE, TenantStatus.TRIAL)),
                    )
                )
                or 0
            ),
            tenants_suspended=int(
                await value(
                    select(func.count())
                    .select_from(Tenant)
                    .where(Tenant.deleted_at.is_(None), Tenant.status == TenantStatus.SUSPENDED)
                )
                or 0
            ),
            posts_total=posts_total,
            posts_removed=int(
                await value(
                    select(func.count()).select_from(Post).where(Post.deleted_at.is_not(None))
                )
                or 0
            ),
            tickets_open=int(
                await value(
                    select(func.count())
                    .select_from(SupportTicket)
                    .where(
                        SupportTicket.deleted_at.is_(None),
                        SupportTicket.status.notin_((TicketStatus.CLOSED,)),
                    )
                )
                or 0
            ),
            tickets_urgent=int(
                await value(
                    select(func.count())
                    .select_from(SupportTicket)
                    .where(
                        SupportTicket.deleted_at.is_(None),
                        SupportTicket.priority == "urgent",
                        SupportTicket.status != TicketStatus.CLOSED,
                    )
                )
                or 0
            ),
            tickets_overdue=int(
                await value(
                    select(func.count())
                    .select_from(SupportTicket)
                    .where(
                        SupportTicket.deleted_at.is_(None),
                        SupportTicket.status.notin_(
                            (TicketStatus.CLOSED, TicketStatus.WAITING_ON_USER)
                        ),
                        SupportTicket.created_at < now - timedelta(days=3),
                    )
                )
                or 0
            ),
            tickets_closed=int(
                await value(
                    select(func.count())
                    .select_from(SupportTicket)
                    .where(
                        SupportTicket.deleted_at.is_(None),
                        SupportTicket.status == TicketStatus.CLOSED,
                    )
                )
                or 0
            ),
        )

    async def users(
        self, q: str | None, status: str | None, limit: int, offset: int
    ) -> list[PlatformUserRead]:
        post_count = (
            select(func.count())
            .select_from(Post)
            .where(Post.author_id == User.id, Post.deleted_at.is_(None))
            .correlate(User)
            .scalar_subquery()
        )
        ticket_count = (
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.requester_id == User.id, SupportTicket.deleted_at.is_(None))
            .correlate(User)
            .scalar_subquery()
        )
        stmt = (
            select(User, Tenant.name, post_count, ticket_count)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(User.deleted_at.is_(None))
        )
        if q:
            term = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(User.full_name.ilike(term), User.email.ilike(term), Tenant.name.ilike(term))
            )
        if status == "active":
            stmt = stmt.where(User.is_active.is_(True))
        if status == "blocked":
            stmt = stmt.where(User.is_active.is_(False))
        rows = (
            await self.session.execute(
                stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
            )
        ).all()
        return [
            PlatformUserRead(
                id=user.id,
                tenant_id=user.tenant_id,
                tenant_name=tenant_name,
                full_name=user.full_name,
                email=user.email,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                is_email_verified=user.is_email_verified,
                mfa_enabled=user.mfa_enabled,
                last_login_at=user.last_login_at,
                posting_restricted_until=user.posting_restricted_until,
                network_profile_removed_at=user.network_profile_removed_at,
                created_at=user.created_at,
                post_count=int(posts or 0),
                ticket_count=int(tickets or 0),
            )
            for user, tenant_name, posts, tickets in rows
        ]

    async def user_detail(self, user_id: uuid.UUID) -> PlatformUserDetail:
        rows = await self.users(None, None, 10000, 0)
        base = next((row for row in rows if row.id == user_id), None)
        if base is None:
            raise NotFoundError("Member not found.")
        connections = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Connection)
                .where(or_(Connection.requester_id == user_id, Connection.addressee_id == user_id))
            )
            or 0
        )
        comments = int(
            await self.session.scalar(
                select(func.count())
                .select_from(Comment)
                .where(Comment.author_id == user_id, Comment.deleted_at.is_(None))
            )
            or 0
        )
        last_ticket = await self.session.scalar(
            select(func.max(SupportTicket.created_at)).where(SupportTicket.requester_id == user_id)
        )
        return PlatformUserDetail(
            **base.model_dump(),
            connection_count=connections,
            comment_count=comments,
            last_ticket_at=last_ticket,
        )

    async def set_user_status(
        self, user_id: uuid.UUID, data: AccountStatusRequest
    ) -> PlatformUserDetail:
        user = await self.session.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        if user is None:
            raise NotFoundError("Member not found.")
        if user.id == self.actor_id and not data.active:
            raise ValidationError("You cannot block your own platform administrator account.")
        if user.is_superuser and not data.active:
            raise ValidationError(
                "Remove platform administrator access before blocking this account."
            )
        user.is_active = data.active
        if not data.active:
            await RefreshTokenRepository(self.session).revoke_all_for_user(user.id)
            await ApiKeyRepository(self.session).revoke_all_for_user(user.tenant_id, user.id)
            user.token_epoch = (user.token_epoch or 0) + 1
            await mark_user_revoked(user.id, user.token_epoch)
        self._audit(
            "member.restored" if data.active else "member.blocked",
            "user",
            user.id,
            data.reason,
            {"email": user.email},
        )
        await self.session.flush()
        return await self.user_detail(user.id)

    async def restrict_posting(
        self, user_id: uuid.UUID, *, days: int | None, reason: str
    ) -> PlatformUserDetail:
        user = await self.session.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        if user is None:
            raise NotFoundError("Member not found.")
        if user.id == self.actor_id and days is not None:
            raise ValidationError("You cannot restrict your own administrator account.")
        user.posting_restricted_until = (
            datetime.now(UTC) + timedelta(days=days) if days is not None else None
        )
        self._audit(
            "member.posting_restricted" if days is not None else "member.posting_restored",
            "user",
            user.id,
            reason,
            {"days": days, "until": user.posting_restricted_until.isoformat() if days else None},
        )
        await self.session.flush()
        return await self.user_detail(user.id)

    async def remove_network_profile(self, user_id: uuid.UUID, *, reason: str) -> None:
        user = await self.session.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        if user is None:
            raise NotFoundError("Member not found.")
        if user.id == self.actor_id or user.is_superuser:
            raise ValidationError("A platform administrator profile cannot be removed here.")
        now = datetime.now(UTC)
        user.network_profile_removed_at = now
        identity = await self.session.scalar(
            select(NetworkIdentity).where(NetworkIdentity.user_id == user_id)
        )
        if identity is not None:
            identity.discoverable = False
            identity.deleted_at = now
        self._audit("member.network_profile_removed", "user", user.id, reason)
        await self.session.flush()

    async def tenants(self, q: str | None, limit: int, offset: int) -> list[PlatformTenantRead]:
        stmt = select(Tenant).where(Tenant.deleted_at.is_(None))
        if q:
            stmt = stmt.where(or_(Tenant.name.ilike(f"%{q}%"), Tenant.slug.ilike(f"%{q}%")))
        tenants = list(
            (
                await self.session.execute(
                    stmt.order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        result: list[PlatformTenantRead] = []
        for tenant in tenants:

            async def count(model, *where) -> int:
                return int(
                    await self.session.scalar(select(func.count()).select_from(model).where(*where))
                    or 0
                )

            result.append(
                PlatformTenantRead(
                    id=tenant.id,
                    name=tenant.name,
                    slug=tenant.slug,
                    status=tenant.status,
                    plan=tenant.plan,
                    type=tenant.type,
                    created_at=tenant.created_at,
                    user_count=await count(
                        User, User.tenant_id == tenant.id, User.deleted_at.is_(None)
                    ),
                    active_user_count=await count(
                        User,
                        User.tenant_id == tenant.id,
                        User.deleted_at.is_(None),
                        User.is_active.is_(True),
                    ),
                    matter_count=await count(
                        Matter, Matter.tenant_id == tenant.id, Matter.deleted_at.is_(None)
                    ),
                    invoice_count=await count(
                        Invoice, Invoice.tenant_id == tenant.id, Invoice.deleted_at.is_(None)
                    ),
                    ticket_count=await count(
                        SupportTicket,
                        SupportTicket.tenant_id == tenant.id,
                        SupportTicket.deleted_at.is_(None),
                    ),
                )
            )
        return result

    async def set_tenant_status(
        self, tenant_id: uuid.UUID, data: TenantStatusRequest
    ) -> PlatformTenantRead:
        tenant = await self.session.scalar(
            select(Tenant).where(Tenant.id == tenant_id, Tenant.deleted_at.is_(None))
        )
        if tenant is None:
            raise NotFoundError("Firm not found.")
        old = str(tenant.status)
        tenant.status = TenantStatus(data.status)
        if tenant.status in (TenantStatus.SUSPENDED, TenantStatus.CANCELLED):
            users = list(
                (
                    await self.session.execute(
                        select(User).where(User.tenant_id == tenant.id, User.deleted_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            for user in users:
                await RefreshTokenRepository(self.session).revoke_all_for_user(user.id)
                user.token_epoch = (user.token_epoch or 0) + 1
                await mark_user_revoked(user.id, user.token_epoch)
        self._audit(
            "firm.status_changed",
            "tenant",
            tenant.id,
            data.reason,
            {"from": old, "to": data.status},
        )
        await self.session.flush()
        return (await self.tenants(tenant.slug, 1, 0))[0]

    async def posts(
        self, q: str | None, include_removed: bool, limit: int, offset: int
    ) -> list[PlatformPostRead]:
        stmt = select(Post)
        if not include_removed:
            stmt = stmt.where(Post.deleted_at.is_(None))
        if q:
            stmt = stmt.where(
                or_(
                    Post.author_name.ilike(f"%{q}%"),
                    Post.title.ilike(f"%{q}%"),
                    Post.content.ilike(f"%{q}%"),
                )
            )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(Post.created_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [PlatformPostRead.model_validate(row, from_attributes=True) for row in rows]

    async def moderate_post(
        self, post_id: uuid.UUID, *, restore: bool, reason: str
    ) -> PlatformPostRead:
        post = await self.session.scalar(select(Post).where(Post.id == post_id))
        if post is None:
            raise NotFoundError("Post not found.")
        post.deleted_at = None if restore else datetime.now(UTC)
        self._audit(
            "post.restored" if restore else "post.removed",
            "post",
            post.id,
            reason,
            {"author": post.author_name},
        )
        return PlatformPostRead.model_validate(post, from_attributes=True)

    async def tickets(self, status: str | None, limit: int, offset: int) -> list[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .where(SupportTicket.deleted_at.is_(None))
            .options(selectinload(SupportTicket.messages))
        )
        if status:
            stmt = stmt.where(SupportTicket.status == status)
        return list(
            (
                await self.session.execute(
                    stmt.order_by(SupportTicket.updated_at.desc()).limit(limit).offset(offset)
                )
            )
            .scalars()
            .all()
        )

    async def update_ticket(
        self, ticket_id: uuid.UUID, data: TicketAdminUpdate, *, actor_name: str
    ) -> SupportTicket:
        ticket = await self.session.scalar(
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id, SupportTicket.deleted_at.is_(None))
            .options(selectinload(SupportTicket.messages))
        )
        if ticket is None:
            raise NotFoundError("Support ticket not found.")
        if data.priority is not None:
            ticket.priority = data.priority
        if data.status is not None:
            ticket.status = data.status
            ticket.closed_at = datetime.now(UTC) if data.status == TicketStatus.CLOSED else None
        if data.assign_to_me:
            ticket.assigned_to_id = self.actor_id
            ticket.assigned_to_name = actor_name
        if data.response:
            # Keep the loaded response collection in sync with the pending row;
            # returning the ticket from the identity map must include the reply.
            ticket.messages.append(
                SupportTicketMessage(
                    tenant_id=ticket.tenant_id,
                    ticket_id=ticket.id,
                    author_id=self.actor_id,
                    author_name=actor_name,
                    is_staff=True,
                    body=data.response,
                )
            )
            ticket.first_response_at = ticket.first_response_at or datetime.now(UTC)
            if data.status is None:
                ticket.status = TicketStatus.WAITING_ON_USER
            await create_notification(
                self.session,
                user_id=ticket.requester_id,
                type=NotificationType.SUPPORT_UPDATE,
                message=f"VidhiSangh Support replied to {ticket.ticket_number}: {ticket.subject}",
                actor_id=self.actor_id,
                actor_name=actor_name,
                link="/app/dashboard",
            )
        self._audit(
            "ticket.updated",
            "support_ticket",
            ticket.id,
            data.response,
            {"status": str(ticket.status), "priority": str(ticket.priority)},
        )
        await self.session.flush()
        return await self.session.scalar(
            select(SupportTicket)
            .where(SupportTicket.id == ticket.id)
            .options(selectinload(SupportTicket.messages))
        )

    async def actions(self, limit: int, offset: int) -> list[PlatformAdminAction]:
        return list(
            (
                await self.session.execute(
                    select(PlatformAdminAction)
                    .where(PlatformAdminAction.deleted_at.is_(None))
                    .order_by(PlatformAdminAction.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
