import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.modules.identity.phone_otp import normalize_phone, send_whatsapp_code


@pytest.mark.parametrize("number", ["9876543210", "919876543210", "+91 98765-43210"])
def test_phone_normalization(number):
    assert normalize_phone(number) == "+919876543210"


async def test_approved_template_and_copy_button(monkeypatch):
    monkeypatch.setattr(settings, "WA_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(settings, "WA_PHONE_NUMBER_ID", "123456")

    async def handle(request):
        import json

        data = json.loads(request.content)
        assert request.url.host == "graph.facebook.com"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert data["to"] == "919876543210"
        template = data["template"]
        assert template["name"] == settings.WA_OTP_TEMPLATE
        assert template["name"] == "vidhisangh_otp"
        body, button = template["components"]
        # The authentication template takes the code alone.
        assert [item["text"] for item in body["parameters"]] == ["123456"]
        assert button["parameters"][0]["text"] == "123456"
        assert button["sub_type"] == "url"
        return httpx.Response(200, json={"messages": [{"id": "mock-id"}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.modules.identity.phone_otp.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    await send_whatsapp_code("+919876543210", "123456")


async def test_older_template_with_call_back_numbers(monkeypatch):
    monkeypatch.setattr(settings, "WA_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(settings, "WA_PHONE_NUMBER_ID", "123456")
    monkeypatch.setattr(settings, "WA_OTP_TEMPLATE_PARAMS", "code,app,expiry,call,contact")
    sent = {}

    async def handle(request):
        import json

        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "mock-id"}]})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.modules.identity.phone_otp.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    await send_whatsapp_code("+919876543210", "123456")
    body = sent["template"]["components"][0]
    assert [p["text"] for p in body["parameters"]] == [
        "123456", "VidhiSangh", "5 minutes", "+917341100692", "+917341100692",
    ]


async def test_provider_errors_do_not_expose_tokens_or_codes(monkeypatch):
    monkeypatch.setattr(settings, "WA_ACCESS_TOKEN", "secret-access-token")
    monkeypatch.setattr(settings, "WA_PHONE_NUMBER_ID", "123456")
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.modules.identity.phone_otp.httpx.AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(400, json={"error": "secret-access-token 123456"})
            ),
            **kwargs,
        ),
    )
    with pytest.raises(ServiceUnavailableError) as error:
        await send_whatsapp_code("+919876543210", "123456")
    assert "123456" not in error.value.message
    assert "secret-access-token" not in error.value.message
