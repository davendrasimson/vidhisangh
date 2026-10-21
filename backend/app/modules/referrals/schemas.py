from __future__ import annotations

from pydantic import BaseModel


# Colleagues who must join through a member's link for the Founding Member badge.
FOUNDING_MEMBER_INVITES = 3


class MyReferral(BaseModel):
    code: str
    link: str
    joined: int
    founding_goal: int = FOUNDING_MEMBER_INVITES
    founding_member: bool = False
