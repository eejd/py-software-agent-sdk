import asyncio
from urllib.parse import parse_qs

from mcp.shared.auth import OAuthClientInformationFull

from openhands.sdk.mcp.oauth import MCPOAuth


def test_authorization_code_exchange_uses_basic_without_duplicate_client_id():
    async def exchange():
        auth = MCPOAuth(
            "http://127.0.0.1:12345/mcp", client_id="client", client_secret="secret"
        )
        auth.context.client_info = OAuthClientInformationFull(
            client_id="client", client_secret="secret",
            token_endpoint_auth_method="client_secret_basic",
        )
        request = await auth._exchange_token_authorization_code("code", "verifier")
        fields = parse_qs(request.content.decode())
        assert fields["code"] == ["code"]
        assert fields["code_verifier"] == ["verifier"]
        assert "authorization" in request.headers and "client_id" not in fields
    asyncio.run(exchange())
