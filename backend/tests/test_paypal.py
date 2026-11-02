"""Tests for PayPal sandbox connectivity service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.paypal import (
    PayPalClient,
    PayPalConfigurationError,
    PayPalAuthenticationError,
    PayPalTimeoutError,
    PayPalOrderError,
    PayPalOrderResponse,
    PayPalCaptureResponse,
    PayPalCaptureError,
    get_paypal_client,
    reset_paypal_client,
)


class TestPayPalClientConfiguration:
    """Tests for PayPal client configuration."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    def test_missing_credentials_raises_error(self):
        """Test that missing credentials raise PayPalConfigurationError."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = None
            mock_settings.return_value.paypal_client_secret = None
            mock_settings.return_value.paypal_environment = "sandbox"

            with pytest.raises(PayPalConfigurationError) as exc_info:
                PayPalClient()

            assert "client_id and client_secret must be configured" in str(exc_info.value)

    def test_missing_client_id_raises_error(self):
        """Test that missing client_id raises PayPalConfigurationError."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = None
            mock_settings.return_value.paypal_client_secret = "secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            with pytest.raises(PayPalConfigurationError) as exc_info:
                PayPalClient()

            assert "client_id and client_secret must be configured" in str(exc_info.value)

    def test_missing_client_secret_raises_error(self):
        """Test that missing client_secret raises PayPalConfigurationError."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "client_id"
            mock_settings.return_value.paypal_client_secret = None
            mock_settings.return_value.paypal_environment = "sandbox"

            with pytest.raises(PayPalConfigurationError) as exc_info:
                PayPalClient()

            assert "client_id and client_secret must be configured" in str(exc_info.value)

    def test_invalid_environment_raises_error(self):
        """Test that invalid (non-sandbox) environment raises PayPalConfigurationError."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "client_id"
            mock_settings.return_value.paypal_client_secret = "secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            with pytest.raises(PayPalConfigurationError) as exc_info:
                PayPalClient(environment="invalid")

            assert "Production/live PayPal mode is not permitted" in str(exc_info.value)

    def test_live_mode_explicitly_rejected(self):
        """Test that explicit live mode raises PayPalConfigurationError.

        This is a focused test confirming live/production mode is rejected
        regardless of settings configuration.
        """
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "live"

            with pytest.raises(PayPalConfigurationError) as exc_info:
                PayPalClient(environment="live")

            error_msg = str(exc_info.value)
            assert "Production/live PayPal mode is not permitted" in error_msg
            assert "environment='live'" in error_msg
            assert "only 'sandbox' is allowed" in error_msg

    def test_settings_live_environment_ignored(self):
        """Test that paypal_environment='live' in settings is ignored/overridden.

        Even if settings has live, the client should force sandbox.
        """
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "live"

            # Should NOT raise - settings live is ignored, sandbox is forced
            client = PayPalClient()
            assert client.environment == "sandbox"
            assert client.base_url == "https://api-m.sandbox.paypal.com"

    def test_valid_sandbox_configuration(self):
        """Test valid sandbox configuration."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()
            assert client.client_id == "test_client_id"
            assert client.client_secret == "test_client_secret"
            assert client.environment == "sandbox"
            assert client.base_url == "https://api-m.sandbox.paypal.com"

    def test_explicit_credentials_override_settings(self):
        """Test that explicit credentials override settings."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "settings_client_id"
            mock_settings.return_value.paypal_client_secret = "settings_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient(
                client_id="explicit_client_id",
                client_secret="explicit_client_secret",
                environment="sandbox",
            )
            assert client.client_id == "explicit_client_id"
            assert client.client_secret == "explicit_client_secret"


class TestPayPalTokenFetch:
    """Tests for PayPal OAuth token fetching."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    @pytest.mark.asyncio
    async def test_fetch_token_success(self):
        """Test successful token fetch."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            # Mock httpx.AsyncClient.post
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "access_token": "A21AAH5B...test_token",
                    "token_type": "Bearer",
                    "expires_in": 32400,
                    "scope": "https://uri.paypal.com/services/invoicing ...",
                    "app_id": "APP-80W284485P519543T",
                    "nonce": "2026-10-31T12:00:00Z",
                }
                mock_post.return_value = mock_response

                token = await client._fetch_token()

                assert token.access_token == "A21AAH5B...test_token"
                assert token.token_type == "Bearer"
                assert token.expires_in == 32400

    @pytest.mark.asyncio
    async def test_fetch_token_invalid_credentials(self):
        """Test token fetch with invalid credentials (401)."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 401
                mock_post.return_value = mock_response

                with pytest.raises(PayPalAuthenticationError) as exc_info:
                    await client._fetch_token()

                assert "Invalid PayPal credentials" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_token_oauth_error(self):
        """Test token fetch with OAuth error response."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.json.return_value = {
                    "error": "invalid_client",
                    "error_description": "Client credentials are invalid",
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalAuthenticationError) as exc_info:
                    await client._fetch_token()

                assert "PayPal OAuth error" in str(exc_info.value)
                assert "Client credentials are invalid" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_token_timeout(self):
        """Test token fetch timeout."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient(timeout=1.0)

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                import httpx
                mock_post.side_effect = httpx.TimeoutException("Request timed out")

                with pytest.raises(PayPalTimeoutError) as exc_info:
                    await client._fetch_token()

                assert "timed out after 1.0s" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_token_network_error(self):
        """Test token fetch network error."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                import httpx
                mock_post.side_effect = httpx.RequestError("Connection failed")

                with pytest.raises(PayPalAuthenticationError) as exc_info:
                    await client._fetch_token()

                assert "PayPal token request failed" in str(exc_info.value)


class TestPayPalGetAccessToken:
    """Tests for get_access_token method."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    @pytest.mark.asyncio
    async def test_get_access_token_caches_token(self):
        """Test that access token is cached and reused."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch.object(client, "_fetch_token", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = MagicMock(
                    access_token="cached_token",
                    token_type="Bearer",
                    expires_in=32400,
                    scope="",
                    app_id="",
                    nonce="",
                )

                # First call
                token1 = await client.get_access_token()
                # Second call (should use cache)
                token2 = await client.get_access_token()

                assert token1 == "cached_token"
                assert token2 == "cached_token"
                # _fetch_token should only be called once
                assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    async def test_get_access_token_refreshes_expired(self):
        """Test that expired token is refreshed."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch.object(client, "_fetch_token", new_callable=AsyncMock) as mock_fetch:
                # First token (expired)
                mock_fetch.return_value = MagicMock(
                    access_token="old_token",
                    token_type="Bearer",
                    expires_in=1,  # Expires in 1 second
                    scope="",
                    app_id="",
                    nonce="",
                )

                token1 = await client.get_access_token()
                assert token1 == "old_token"

                # Simulate time passing (token expired)
                client._token_expires_at = 0

                # Second call with new token
                mock_fetch.return_value = MagicMock(
                    access_token="new_token",
                    token_type="Bearer",
                    expires_in=32400,
                    scope="",
                    app_id="",
                    nonce="",
                )

                token2 = await client.get_access_token()
                assert token2 == "new_token"
                assert mock_fetch.call_count == 2


class TestPayPalMakeRequest:
    """Tests for _make_request method."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    @pytest.mark.asyncio
    async def test_make_request_success(self):
        """Test successful API request."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.return_value = "test_access_token"

                with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"id": "PAY-123", "status": "COMPLETED"}
                    mock_request.return_value = mock_response

                    result = await client._make_request("GET", "/v2/payments/captures/TEST")

                    assert result == {"id": "PAY-123", "status": "COMPLETED"}
                    mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_401_refreshes_token(self):
        """Test that 401 response triggers token refresh and retry."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.side_effect = ["old_token", "new_token"]

                with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
                    # First response: 401
                    mock_response_401 = MagicMock()
                    mock_response_401.status_code = 401
                    # Second response: 200
                    mock_response_200 = MagicMock()
                    mock_response_200.status_code = 200
                    mock_response_200.json.return_value = {"id": "PAY-123"}

                    mock_request.side_effect = [mock_response_401, mock_response_200]

                    result = await client._make_request("GET", "/v2/payments/captures/TEST")

                    assert result == {"id": "PAY-123"}
                    assert mock_request.call_count == 2
                    assert mock_get_token.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_api_error(self):
        """Test API error response."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.return_value = "test_access_token"

                with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
                    mock_response = MagicMock()
                    mock_response.status_code = 404
                    mock_response.json.return_value = {
                        "name": "RESOURCE_NOT_FOUND",
                        "message": "Capture not found",
                    }
                    mock_request.return_value = mock_response

                    with pytest.raises(PayPalAuthenticationError) as exc_info:
                        await client._make_request("GET", "/v2/payments/captures/INVALID")

                    assert "PayPal API error (404)" in str(exc_info.value)
                    assert "Capture not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_make_request_timeout(self):
        """Test API request timeout."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient(timeout=1.0)

            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.return_value = "test_access_token"

                with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
                    import httpx
                    mock_request.side_effect = httpx.TimeoutException("Request timed out")

                    with pytest.raises(PayPalTimeoutError) as exc_info:
                        await client._make_request("GET", "/v2/payments/captures/TEST")

                    assert "timed out after 1.0s" in str(exc_info.value)


class TestPayPalVerifyConnection:
    """Tests for verify_connection method."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    @pytest.mark.asyncio
    async def test_verify_connection_success(self):
        """Test successful connection verification."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.return_value = "test_token"

                result = await client.verify_connection()
                assert result is True

    @pytest.mark.asyncio
    async def test_verify_connection_failure(self):
        """Test connection verification failure."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client = PayPalClient()

            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.side_effect = PayPalAuthenticationError("Auth failed")

                with pytest.raises(PayPalAuthenticationError):
                    await client.verify_connection()


class TestPayPalSingleton:
    """Tests for singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    def test_get_paypal_client_returns_singleton(self):
        """Test that get_paypal_client returns singleton instance."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client1 = get_paypal_client()
            client2 = get_paypal_client()

            assert client1 is client2

    def test_reset_paypal_client(self):
        """Test that reset_paypal_client creates new instance."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"

            client1 = get_paypal_client()
            reset_paypal_client()
            client2 = get_paypal_client()

            assert client1 is not client2


class TestPayPalCreateOrder:
    """Tests for create_order method."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    def _make_client(self, timeout: float = 10.0):
        """Create a test client with mocked settings."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"
            return PayPalClient(timeout=timeout)

    @pytest.mark.asyncio
    async def test_create_order_success(self):
        """Test successful order creation with approval URL extraction."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "CREATED",
                    "links": [
                        {
                            "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T",
                            "rel": "self",
                            "method": "GET",
                        },
                        {
                            "href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
                            "rel": "approve",
                            "method": "GET",
                        },
                        {
                            "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T/capture",
                            "rel": "capture",
                            "method": "POST",
                        },
                    ],
                    "create_time": "2024-01-15T10:00:00Z",
                    "update_time": "2024-01-15T10:00:00Z",
                }
                mock_post.return_value = mock_response

                result = await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert isinstance(result, PayPalOrderResponse)
                assert result.order_id == "5O190127TN364715T"
                assert result.status == "CREATED"
                assert result.approval_url == "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T"
                assert result.create_time == "2024-01-15T10:00:00Z"
                assert result.update_time == "2024-01-15T10:00:00Z"
                assert len(result.links) == 3

    @pytest.mark.asyncio
    async def test_create_order_exact_cents_conversion(self):
        """Test exact conversion of integer cents to PayPal amount string."""
        client = self._make_client()

        # Test various cent amounts
        test_cases = [
            (1, "0.01"),
            (99, "0.99"),
            (100, "1.00"),
            (101, "1.01"),
            (10000, "100.00"),
            (12345, "123.45"),
            (999999, "9999.99"),
        ]

        for amount_cents, expected_amount in test_cases:
            assert client._cents_to_amount_string(amount_cents) == expected_amount

    @pytest.mark.asyncio
    async def test_create_order_invalid_amount_zero(self):
        """Test that zero amount is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=0, currency="USD", request_id="test-req-123")

        assert "amount_cents must be a positive integer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_amount_negative(self):
        """Test that negative amount is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=-100, currency="USD", request_id="test-req-123")

        assert "amount_cents must be a positive integer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_amount_float(self):
        """Test that float amount is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=100.5, currency="USD", request_id="test-req-123")  # type: ignore

        assert "amount_cents must be a positive integer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_rejects_bool_amount(self):
        """Test that bool amount is rejected (bool is subclass of int in Python)."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=True, currency="USD", request_id="test-req-123")  # type: ignore

        assert "amount_cents must be a positive integer" in str(exc_info.value)

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=False, currency="USD", request_id="test-req-123")  # type: ignore

        assert "amount_cents must be a positive integer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_currency_lowercase(self):
        """Test that lowercase currency is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="usd", request_id="test-req-123")

        assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_currency_too_short(self):
        """Test that short currency code is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="US", request_id="test-req-123")

        assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_currency_too_long(self):
        """Test that long currency code is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="USDD", request_id="test-req-123")

        assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_currency_with_numbers(self):
        """Test that currency with numbers is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="US1", request_id="test-req-123")

        assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_currency_eur(self):
        """Test that EUR is rejected (USD only for hackathon)."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="EUR", request_id="test-req-123")

        assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_invalid_currency_gbp(self):
        """Test that GBP is rejected (USD only for hackathon)."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="GBP", request_id="test-req-123")

        assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_missing_approval_url(self):
        """Test handling of missing approval URL in response."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                # No approve link in response
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "CREATED",
                    "links": [
                        {
                            "href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T",
                            "rel": "self",
                            "method": "GET",
                        },
                    ],
                    "create_time": "2024-01-15T10:00:00Z",
                    "update_time": "2024-01-15T10:00:00Z",
                }
                mock_post.return_value = mock_response

                result = await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert result.order_id == "5O190127TN364715T"
                assert result.approval_url is None

    @pytest.mark.asyncio
    async def test_create_order_missing_order_id(self):
        """Test handling of missing order ID in response."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                # Missing 'id' field
                mock_response.json.return_value = {
                    "status": "CREATED",
                    "links": [],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalOrderError) as exc_info:
                    await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert "PayPal response missing order ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_paypal_api_error(self):
        """Test handling of PayPal API error response."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_response.json.return_value = {
                    "name": "INVALID_REQUEST",
                    "message": "Invalid purchase unit amount",
                    "debug_id": "abc123",
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalOrderError) as exc_info:
                    await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert "PayPal order creation failed (400)" in str(exc_info.value)
                assert "Invalid purchase unit amount" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_timeout(self):
        """Test handling of request timeout."""
        client = self._make_client(timeout=1.0)

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                import httpx
                mock_post.side_effect = httpx.TimeoutException("Request timed out")

                with pytest.raises(PayPalTimeoutError) as exc_info:
                    await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert "timed out after 1.0s" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_network_error(self):
        """Test handling of network error."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                import httpx
                mock_post.side_effect = httpx.RequestError("Connection failed")

                with pytest.raises(PayPalAuthenticationError) as exc_info:
                    await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert "PayPal order request failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_stable_request_id(self):
        """Test that stable PayPal-Request-Id is used when provided."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "CREATED",
                    "links": [],
                    "create_time": "2024-01-15T10:00:00Z",
                    "update_time": "2024-01-15T10:00:00Z",
                }
                mock_post.return_value = mock_response

                # Call with explicit request_id
                await client.create_order(
                    amount_cents=10000,
                    currency="USD",
                    request_id="my-stable-idempotency-key-123",
                )

                # Verify the request was made with the custom request_id
                call_args = mock_post.call_args
                headers = call_args.kwargs.get("headers", {})
                assert headers.get("PayPal-Request-Id") == "my-stable-idempotency-key-123"

    @pytest.mark.asyncio
    async def test_create_order_requires_request_id(self):
        """Test that missing request_id is rejected before network request."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="USD", request_id="")

        assert "request_id is required for idempotency" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_rejects_whitespace_request_id(self):
        """Test that whitespace-only request_id is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="USD", request_id="   ")

        assert "request_id is required for idempotency" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_rejects_long_request_id(self):
        """Test that request_id exceeding 108 characters is rejected."""
        client = self._make_client()
        long_id = "x" * 109

        with pytest.raises(PayPalOrderError) as exc_info:
            await client.create_order(amount_cents=10000, currency="USD", request_id=long_id)

        assert "request_id exceeds 108 characters" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_order_401_refreshes_token(self):
        """Test that 401 response triggers token refresh and retry with same request_id."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.side_effect = ["old_token", "new_token"]

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                # First response: 401
                mock_response_401 = MagicMock()
                mock_response_401.status_code = 401
                # Second response: 201
                mock_response_201 = MagicMock()
                mock_response_201.status_code = 201
                mock_response_201.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "CREATED",
                    "links": [],
                    "create_time": "2024-01-15T10:00:00Z",
                    "update_time": "2024-01-15T10:00:00Z",
                }
                mock_post.side_effect = [mock_response_401, mock_response_201]

                result = await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert result.order_id == "5O190127TN364715T"
                assert mock_post.call_count == 2
                assert mock_get_token.call_count == 2
                # Verify same request_id used on both requests
                for call in mock_post.call_args_list:
                    headers = call.kwargs.get("headers", {})
                    assert headers.get("PayPal-Request-Id") == "test-req-123"

    @pytest.mark.asyncio
    async def test_create_order_payer_action_link(self):
        """Test extraction of approval URL from payer-action link when approve link missing."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                # Only payer-action link, no approve link
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "CREATED",
                    "links": [
                        {
                            "href": "https://www.sandbox.paypal.com/webapps/hermes/payer-action?token=5O190127TN364715T",
                            "rel": "payer-action",
                            "method": "GET",
                        },
                    ],
                    "create_time": "2024-01-15T10:00:00Z",
                    "update_time": "2024-01-15T10:00:00Z",
                }
                mock_post.return_value = mock_response

                result = await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")

                assert result.order_id == "5O190127TN364715T"
                assert result.approval_url == "https://www.sandbox.paypal.com/webapps/hermes/payer-action?token=5O190127TN364715T"

    @pytest.mark.asyncio
    async def test_create_order_only_usd_accepted(self):
        """Test that only USD is accepted (hackathon restriction)."""
        client = self._make_client()

        # USD should succeed
        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "ORDER-USD",
                    "status": "CREATED",
                    "links": [],
                    "create_time": "2024-01-15T10:00:00Z",
                    "update_time": "2024-01-15T10:00:00Z",
                }
                mock_post.return_value = mock_response

                result = await client.create_order(amount_cents=10000, currency="USD", request_id="test-req-123")
                assert result.order_id == "ORDER-USD"

        # Non-USD currencies should be rejected before network request
        invalid_currencies = ["EUR", "GBP", "JPY", "CAD", "AUD", "usd", "Usd", "US", "USDD", "US1", "123", "", " "]

        for currency in invalid_currencies:
            with pytest.raises(PayPalOrderError) as exc_info:
                await client.create_order(amount_cents=10000, currency=currency, request_id="test-req-123")
            assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cents_to_amount_string_edge_cases(self):
        """Test edge cases for cents to amount string conversion."""
        client = self._make_client()

        # Test zero
        assert client._cents_to_amount_string(0) == "0.00"

        # Test large numbers
        assert client._cents_to_amount_string(1000000) == "10000.00"
        assert client._cents_to_amount_string(99999999) == "999999.99"

    @pytest.mark.asyncio
    async def test_cents_to_amount_string_negative_raises(self):
        """Test that negative cents raises ValueError."""
        client = self._make_client()

        with pytest.raises(ValueError) as exc_info:
            client._cents_to_amount_string(-1)

        assert "amount_cents must be non-negative" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_currency_valid(self):
        """Test currency validation with valid codes (USD only)."""
        client = self._make_client()

        assert client._validate_currency("USD") == "USD"

    @pytest.mark.asyncio
    async def test_validate_currency_invalid_cases(self):
        """Test currency validation rejects non-USD codes."""
        client = self._make_client()

        invalid_currencies = ["usd", "UsD", "US", "USDD", "US1", "123", "", " ", "EUR", "GBP", "JPY"]

        for currency in invalid_currencies:
            with pytest.raises(PayPalOrderError) as exc_info:
                client._validate_currency(currency)
            assert "currency must be USD" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_request_id_valid(self):
        """Test request_id validation with valid IDs."""
        client = self._make_client()

        assert client._validate_request_id("test-req-123") == "test-req-123"
        assert client._validate_request_id("uuid-12345678-1234-1234-1234-123456789012") == "uuid-12345678-1234-1234-1234-123456789012"
        assert client._validate_request_id("a" * 108) == "a" * 108

    @pytest.mark.asyncio
    async def test_validate_request_id_empty(self):
        """Test request_id validation rejects empty string."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            client._validate_request_id("")
        assert "request_id is required for idempotency" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_request_id_whitespace(self):
        """Test request_id validation rejects whitespace-only string."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            client._validate_request_id("   ")
        assert "request_id is required for idempotency" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_request_id_too_long(self):
        """Test request_id validation rejects IDs longer than 108 chars."""
        client = self._make_client()

        with pytest.raises(PayPalOrderError) as exc_info:
            client._validate_request_id("x" * 109)
        assert "request_id exceeds 108 characters" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_request_id_strips_whitespace(self):
        """Test request_id validation strips surrounding whitespace."""
        client = self._make_client()

        assert client._validate_request_id("  test-id  ") == "test-id"


class TestPayPalCaptureOrder:
    """Tests for capture_order method."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_paypal_client()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_paypal_client()

    def _make_client(self, timeout: float = 10.0):
        """Create a test client with mocked settings."""
        with patch("app.services.paypal.get_settings") as mock_settings:
            mock_settings.return_value.paypal_client_id = "test_client_id"
            mock_settings.return_value.paypal_client_secret = "test_client_secret"
            mock_settings.return_value.paypal_environment = "sandbox"
            return PayPalClient(timeout=timeout)

    @pytest.mark.asyncio
    async def test_capture_order_success(self):
        """Test successful capture with correct PayPal response structure."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                # Correct PayPal response structure:
                # Top-level id = ORDER_ID, nested capture.id = CAPTURE_ID
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",  # ORDER ID (top-level)
                    "status": "COMPLETED",       # ORDER status (top-level)
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "8C7654321D9876543",  # CAPTURE ID (nested)
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "123.45",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                    "create_time": "2024-01-15T10:05:00Z",
                    "update_time": "2024-01-15T10:05:00Z",
                    "links": [
                        {
                            "href": "https://api-m.sandbox.paypal.com/v2/payments/captures/8C7654321D9876543",
                            "rel": "self",
                            "method": "GET",
                        },
                        {
                            "href": "https://api-m.sandbox.paypal.com/v2/payments/captures/8C7654321D9876543/refund",
                            "rel": "refund",
                            "method": "POST",
                        },
                    ],
                }
                mock_post.return_value = mock_response

                result = await client.capture_order(
                    order_id="5O190127TN364715T",
                    request_id="capture-req-123",
                )

                assert isinstance(result, PayPalCaptureResponse)
                # capture_id comes from NESTED capture object
                assert result.capture_id == "8C7654321D9876543"
                assert result.capture_status == "COMPLETED"
                # order_id comes from TOP-LEVEL id
                assert result.order_id == "5O190127TN364715T"
                assert result.order_status == "COMPLETED"
                assert result.currency == "USD"
                # Exact cents conversion: 123.45 -> 12345
                assert result.amount_cents == 12345
                assert result.create_time == "2024-01-15T10:05:00Z"
                assert result.update_time == "2024-01-15T10:05:00Z"
                assert len(result.links) == 2

    @pytest.mark.asyncio
    async def test_capture_order_order_id_mismatch_rejected(self):
        """Test that order_id mismatch between request and response is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                # Response has DIFFERENT order ID than requested
                mock_response.json.return_value = {
                    "id": "DIFFERENT_ORDER_ID",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "Order ID mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_capture_order_missing_nested_captures(self):
        """Test that missing captures array is rejected (not defaulted)."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                # No captures array
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "missing captures array" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_missing_nested_capture_id(self):
        """Test that missing nested capture.id is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        # Missing 'id' in capture
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "missing capture id" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_missing_amount(self):
        """Test that missing amount in capture is rejected (not defaulted to zero)."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        # Missing amount entirely
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "missing amount" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_missing_currency(self):
        """Test that missing currency_code is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        "amount": {
                                            # Missing currency_code
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "missing currency_code" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_missing_value(self):
        """Test that missing value in amount is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            # Missing value
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "missing value" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_malformed_amount_value(self):
        """Test that malformed amount value is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "not-a-number",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "malformed amount" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_too_many_decimal_places(self):
        """Test that amount with >2 decimal places is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.123",  # 3 decimal places
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "too many decimal places" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_negative_amount_rejected(self):
        """Test that negative amount is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "-100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "non-negative" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_non_usd_currency_rejected(self):
        """Test that non-USD currency is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "EUR",  # Not USD
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "unsupported currency" in str(exc_info.value).lower()
                assert "eur" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_multiple_purchase_units_rejected(self):
        """Test that multiple purchase_units are rejected (fail closed)."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_1",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "50.00",
                                        },
                                    }
                                ]
                            }
                        },
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_2",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "50.00",
                                        },
                                    }
                                ]
                            }
                        },
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "expected exactly 1 purchase_unit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_multiple_captures_rejected(self):
        """Test that multiple captures in one purchase_unit are rejected (fail closed)."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_1",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "50.00",
                                        },
                                    },
                                    {
                                        "id": "CAPTURE_2",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "50.00",
                                        },
                                    },
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "expected exactly 1 capture" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_non_completed_capture_status_rejected(self):
        """Test that non-COMPLETED capture status is rejected."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 201
                mock_response.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "CAPTURE_123",
                                        "status": "PENDING",  # Not COMPLETED
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "not completed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_invalid_order_id_chars(self):
        """Test that order_id with path separators/URL chars is rejected."""
        client = self._make_client()

        # Test various invalid characters
        invalid_ids = [
            "order/with/slash",
            "order?query=1",
            "order#fragment",
            "order with spaces",
            "order@domain",
            "order:colon",
            "order;semicolon",
            "order|pipe",
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(PayPalCaptureError) as exc_info:
                await client.capture_order(order_id=invalid_id, request_id="capture-req-123")
            assert "invalid characters" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_order_valid_order_id_chars(self):
        """Test that valid order_id characters are accepted."""
        client = self._make_client()

        # These should be valid (alphanumeric, hyphen, underscore)
        valid_ids = [
            "5O190127TN364715T",
            "ORDER-123",
            "order_456",
            "ABC123",
            "a-b-c_123",
        ]

        for valid_id in valid_ids:
            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.return_value = "test_access_token"

                with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 201
                    mock_response.json.return_value = {
                        "id": valid_id,
                        "status": "COMPLETED",
                        "purchase_units": [
                            {
                                "payments": {
                                    "captures": [
                                        {
                                            "id": "CAPTURE_123",
                                            "status": "COMPLETED",
                                            "amount": {
                                                "currency_code": "USD",
                                                "value": "100.00",
                                            },
                                        }
                                    ]
                                }
                            }
                        ],
                    }
                    mock_post.return_value = mock_response

                    # Should not raise validation error
                    result = await client.capture_order(order_id=valid_id, request_id="capture-req-123")
                    assert result.order_id == valid_id

    @pytest.mark.asyncio
    async def test_capture_order_exact_cents_conversion(self):
        """Test exact decimal string to cents conversion (no float)."""
        client = self._make_client()

        test_cases = [
            ("0.01", 1),
            ("0.99", 99),
            ("1.00", 100),
            ("1.01", 101),
            ("100.00", 10000),
            ("123.45", 12345),
            ("9999.99", 999999),
            ("0.10", 10),
        ]

        for value_str, expected_cents in test_cases:
            with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
                mock_get_token.return_value = "test_access_token"

                with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                    mock_response = MagicMock()
                    mock_response.status_code = 201
                    mock_response.json.return_value = {
                        "id": "5O190127TN364715T",
                        "status": "COMPLETED",
                        "purchase_units": [
                            {
                                "payments": {
                                    "captures": [
                                        {
                                            "id": "CAPTURE_123",
                                            "status": "COMPLETED",
                                            "amount": {
                                                "currency_code": "USD",
                                                "value": value_str,
                                            },
                                        }
                                    ]
                                }
                            }
                        ],
                    }
                    mock_post.return_value = mock_response

                    result = await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")
                    assert result.amount_cents == expected_cents, f"Failed for {value_str}: got {result.amount_cents}, expected {expected_cents}"

    @pytest.mark.asyncio
    async def test_capture_order_invalid_order_id_empty(self):
        """Test that empty order_id is rejected before network request."""
        client = self._make_client()

        with pytest.raises(PayPalCaptureError) as exc_info:
            await client.capture_order(order_id="", request_id="capture-req-123")

        assert "order_id is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_capture_order_invalid_order_id_too_long(self):
        """Test that order_id exceeding 64 chars is rejected."""
        client = self._make_client()
        long_id = "x" * 65

        with pytest.raises(PayPalCaptureError) as exc_info:
            await client.capture_order(order_id=long_id, request_id="capture-req-123")

        assert "order_id exceeds 64 characters" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_capture_order_invalid_request_id_empty(self):
        """Test that empty request_id is rejected."""
        client = self._make_client()

        with pytest.raises(PayPalCaptureError) as exc_info:
            await client.capture_order(order_id="5O190127TN364715T", request_id="")

        assert "request_id is required for idempotency" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_capture_order_invalid_request_id_too_long(self):
        """Test that request_id exceeding 108 chars is rejected."""
        client = self._make_client()
        long_id = "x" * 109

        with pytest.raises(PayPalCaptureError) as exc_info:
            await client.capture_order(order_id="5O190127TN364715T", request_id=long_id)

        assert "request_id exceeds 108 characters" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_capture_order_paypal_api_error(self):
        """Test handling of PayPal API error response."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 422
                mock_response.json.return_value = {
                    "name": "ORDER_NOT_APPROVED",
                    "message": "The order is not approved",
                    "debug_id": "abc123",
                }
                mock_post.return_value = mock_response

                with pytest.raises(PayPalCaptureError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "PayPal capture failed (422)" in str(exc_info.value)
                assert "The order is not approved" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_capture_order_timeout(self):
        """Test handling of capture request timeout."""
        client = self._make_client(timeout=1.0)

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.return_value = "test_access_token"

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                import httpx
                mock_post.side_effect = httpx.TimeoutException("Request timed out")

                with pytest.raises(PayPalTimeoutError) as exc_info:
                    await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert "timed out after 1.0s" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_capture_order_401_refreshes_token(self):
        """Test that 401 response triggers token refresh and retry with same request_id."""
        client = self._make_client()

        with patch.object(client, "get_access_token", new_callable=AsyncMock) as mock_get_token:
            mock_get_token.side_effect = ["old_token", "new_token"]

            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                # First response: 401
                mock_response_401 = MagicMock()
                mock_response_401.status_code = 401
                # Second response: 201 (with correct structure)
                mock_response_201 = MagicMock()
                mock_response_201.status_code = 201
                mock_response_201.json.return_value = {
                    "id": "5O190127TN364715T",
                    "status": "COMPLETED",
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [
                                    {
                                        "id": "8C7654321D9876543",
                                        "status": "COMPLETED",
                                        "amount": {
                                            "currency_code": "USD",
                                            "value": "100.00",
                                        },
                                    }
                                ]
                            }
                        }
                    ],
                    "create_time": "2024-01-15T10:05:00Z",
                    "update_time": "2024-01-15T10:05:00Z",
                    "links": [],
                }
                mock_post.side_effect = [mock_response_401, mock_response_201]

                result = await client.capture_order(order_id="5O190127TN364715T", request_id="capture-req-123")

                assert result.capture_id == "8C7654321D9876543"
                assert result.amount_cents == 10000
                assert mock_post.call_count == 2
                assert mock_get_token.call_count == 2
                # Verify same request_id used on both requests
                for call in mock_post.call_args_list:
                    headers = call.kwargs.get("headers", {})
                    assert headers.get("PayPal-Request-Id") == "capture-req-123"