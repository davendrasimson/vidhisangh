from __future__ import annotations

from pydantic import BaseModel


class MyReferral(BaseModel):
    code: str
    link: str
    joined: int
