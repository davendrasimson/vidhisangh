"""Token-only unsubscribe: GET confirms; only POST changes the subscription."""

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

from app.core.deps import AuthSessionDep
from app.modules.research.daily_orders import unsubscribe

router = APIRouter(prefix="/research/daily-orders", tags=["Daily Supreme Court orders"])


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def confirm_unsubscribe(token: str) -> HTMLResponse:
    # Email scanners routinely follow GET links: do not withdraw consent here.
    return HTMLResponse(
        "<!doctype html><html lang='en'><meta name='viewport' content='width=device-width'>"
        "<title>Unsubscribe — VidhiSangh</title><body><h1>Supreme Court order emails</h1>"
        "<form method='post'><button>Unsubscribe</button></form></body></html>",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.post("/unsubscribe/{token}", status_code=204)
async def unsubscribe_orders(token: str, session: AuthSessionDep) -> Response:
    await unsubscribe(session, token)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
