"""PayPal sandbox connectivity service.

Implements OAuth 2.0 client credentials flow for PayPal sandbox API ONLY.
Base URL: https://api-m.sandbox.paypal.com

Production/live mode is explicitly REJECTED for security.
"""

import base64
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from app.core.config import get_settings


@dataclass
class PayPalTokenResponse:
    """Response from PayPal OAuth token endpoint."""
    access_token: str
    token_type: str
    expires_in: int
    scope: str
    app_id: str
    nonce: str


@dataclass
class PayPalErrorResponse:
    """Error response from PayPal API."""
    error: str
    error_description: str
    debug_id: str


class PayPalConfigurationError(Exception):
    """Raised when PayPal configuration is missing or invalid."""
    pass


class PayPalAuthenticationError(Exception):
    """Raised when PayPal authentication fails."""
    pass


class PayPalTimeoutError(Exception):
    """Raised when PayPal API request times out."""
    pass


@dataclass
class PayPalOrderResponse:
    """Response from PayPal Orders v2 create endpoint."""
    order_id: str
    status: str
    approval_url: Optional[str]
    payer_id: Optional[str]
    create_time: str
    update_time: str
    links: list


class PayPalOrderError(Exception):
    """Raised when PayPal order creation fails."""
    pass


class PayPalCaptureError(Exception):
    """Raised when PayPal order capture fails."""
    pass


@dataclass
class PayPalCaptureResponse:
    """Response from PayPal Orders v2 capture endpoint."""
    capture_id: str
    capture_status: str
    order_id: str
    order_status: str
    currency: str
    amount_cents: int
    create_time: str
    update_time: str
    links: list


class PayPalClient:
    """PayPal SANDBOX-ONLY API client with OAuth 2.0 client credentials flow.

    Production/live PayPal endpoints are explicitly REJECTED.
    Only https://api-m.sandbox.paypal.com is supported.
    """

    # PayPal sandbox base URL (ONLY supported endpoint)
    SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"

    # OAuth token endpoint
    TOKEN_ENDPOINT = "/v1/oauth2/token"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        environment: Optional[str] = None,
        timeout: float = 10.0,
    ):
        """Initialize PayPal SANDBOX-ONLY client.

        Args:
            client_id: PayPal client ID (defaults to settings)
            client_secret: PayPal client secret (defaults to settings)
            environment: MUST be "sandbox" (defaults to settings, then "sandbox").
                         "live" or any other value raises PayPalConfigurationError.
            timeout: Request timeout in seconds

        Raises:
            PayPalConfigurationError: If environment is not "sandbox".
        """
        settings = get_settings()

        self.client_id = client_id or settings.paypal_client_id
        self.client_secret = client_secret or settings.paypal_client_secret
        # Force sandbox-only: ignore any configured environment, default to sandbox
        self.environment = "sandbox"
        self.timeout = timeout

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        if not self.client_id or not self.client_secret:
            raise PayPalConfigurationError(
                "PayPal client_id and client_secret must be configured. "
                "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET environment variables."
            )

        # Explicitly reject live/production mode
        if environment is not None and environment != "sandbox":
            raise PayPalConfigurationError(
                f"Production/live PayPal mode is not permitted. "
                f"Received environment='{environment}', only 'sandbox' is allowed. "
                f"This is a security restriction for the hackathon."
            )

    @property
    def base_url(self) -> str:
        """Get base URL - ALWAYS returns sandbox endpoint."""
        return self.SANDBOX_BASE_URL

    @property
    def token_url(self) -> str:
        """Get full token endpoint URL - ALWAYS sandbox."""
        return f"{self.base_url}{self.TOKEN_ENDPOINT}"

    def _get_auth_header(self) -> str:
        """Generate Basic auth header for client credentials."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    async def _fetch_token(self) -> PayPalTokenResponse:
        """Fetch new access token from PayPal OAuth endpoint.

        Returns:
            PayPalTokenResponse with access token and metadata.

        Raises:
            PayPalAuthenticationError: If authentication fails.
            PayPalTimeoutError: If request times out.
        """
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        data = {
            "grant_type": "client_credentials",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.token_url,
                    headers=headers,
                    data=data,
                )

                if response.status_code == 401:
                    raise PayPalAuthenticationError(
                        "Invalid PayPal credentials. Check client_id and client_secret."
                    )

                if response.status_code != 200:
                    error_data = response.json()
                    raise PayPalAuthenticationError(
                        f"PayPal OAuth error: {error_data.get('error_description', 'Unknown error')}"
                    )

                token_data = response.json()
                return PayPalTokenResponse(
                    access_token=token_data["access_token"],
                    token_type=token_data.get("token_type", "Bearer"),
                    expires_in=token_data.get("expires_in", 32400),
                    scope=token_data.get("scope", ""),
                    app_id=token_data.get("app_id", ""),
                    nonce=token_data.get("nonce", ""),
                )

        except httpx.TimeoutException:
            raise PayPalTimeoutError(f"PayPal token request timed out after {self.timeout}s")
        except httpx.RequestError as e:
            raise PayPalAuthenticationError(f"PayPal token request failed: {str(e)}")

    async def get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary.

        Returns:
            Valid PayPal access token.

        Raises:
            PayPalConfigurationError: If credentials not configured.
            PayPalAuthenticationError: If authentication fails.
            PayPalTimeoutError: If request times out.
        """
        # Check if current token is still valid (with 60s buffer)
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        # Fetch new token
        token_response = await self._fetch_token()

        self._access_token = token_response.access_token
        self._token_expires_at = time.time() + token_response.expires_in

        return self._access_token

    async def _make_request(
        self,
        method: str,
        path: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Make authenticated request to PayPal API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/v2/payments/captures/{capture_id}")
            json_data: JSON body for POST/PUT requests
            params: Query parameters

        Returns:
            Parsed JSON response.

        Raises:
            PayPalAuthenticationError: If authentication fails.
            PayPalTimeoutError: If request times out.
        """
        token = await self.get_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "PayPal-Request-Id": f"req-{int(time.time() * 1000)}",
        }

        url = f"{self.base_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                )

                if response.status_code == 401:
                    # Token may have expired, force refresh and retry once
                    self._access_token = None
                    self._token_expires_at = 0
                    token = await self.get_access_token()
                    headers["Authorization"] = f"Bearer {token}"

                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=json_data,
                        params=params,
                    )

                if response.status_code >= 400:
                    error_data = response.json()
                    raise PayPalAuthenticationError(
                        f"PayPal API error ({response.status_code}): "
                        f"{error_data.get('message', 'Unknown error')}"
                    )

                return response.json()

        except httpx.TimeoutException:
            raise PayPalTimeoutError(f"PayPal API request timed out after {self.timeout}s")
        except httpx.RequestError as e:
            raise PayPalAuthenticationError(f"PayPal API request failed: {str(e)}")

    async def get(self, path: str, params: Optional[dict] = None) -> dict:
        """Make GET request to PayPal API."""
        return await self._make_request("GET", path, params=params)

    async def post(self, path: str, json_data: Optional[dict] = None) -> dict:
        """Make POST request to PayPal API."""
        return await self._make_request("POST", path, json_data=json_data)

    async def patch(self, path: str, json_data: Optional[dict] = None) -> dict:
        """Make PATCH request to PayPal API."""
        return await self._make_request("PATCH", path, json_data=json_data)

    @staticmethod
    def _cents_to_amount_string(amount_cents: int) -> str:
        """Convert integer cents to exact two-decimal PayPal amount string.

        Uses integer arithmetic to avoid floating-point precision issues.
        Example: 12345 cents -> "123.45"
        """
        if amount_cents < 0:
            raise ValueError("amount_cents must be non-negative")
        dollars = amount_cents // 100
        cents = amount_cents % 100
        return f"{dollars}.{cents:02d}"

    @staticmethod
    def _validate_currency(currency: str) -> str:
        """Validate currency code - restricted to USD for hackathon."""
        if currency != "USD":
            raise PayPalOrderError("currency must be USD (hackathon restriction)")
        return currency

    @staticmethod
    def _validate_request_id(request_id: str) -> str:
        """Validate PayPal-Request-Id against PayPal constraints.

        PayPal requires:
        - Non-empty string
        - Maximum 108 characters (Orders v2 documented maximum)
        - Used for idempotency: same ID returns same response
        """
        if not request_id or not request_id.strip():
            raise PayPalOrderError("request_id is required for idempotency")
        request_id = request_id.strip()
        if len(request_id) > 108:
            raise PayPalOrderError("request_id exceeds 108 characters")
        return request_id

    async def create_order(
        self,
        amount_cents: int,
        currency: str,
        request_id: str,
    ) -> PayPalOrderResponse:
        """Create a PayPal Order v2 with CAPTURE intent.

        This is internal plumbing only. The future payment orchestration layer
        must derive amount, currency, merchant context and idempotency from a
        verified ALLOW authorization decision with an active RESERVED reservation.

        Args:
            amount_cents: Transaction amount in minor units (cents). Must be positive.
            currency: Must be "USD" (hackathon restriction).
            request_id: Stable request ID for PayPal-Request-Id header
                       to support retry idempotency. Must be non-empty,
                       max 255 characters. Same ID must be used on retry.

        Returns:
            PayPalOrderResponse with order_id, status, approval_url, and metadata.

        Raises:
            PayPalConfigurationError: If credentials not configured.
            PayPalOrderError: If amount/currency/request_id validation fails
                             or PayPal API returns error.
            PayPalAuthenticationError: If authentication fails.
            PayPalTimeoutError: If request times out.
        """
        # Validate amount (reject bool since bool is subclass of int in Python)
        if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
            raise PayPalOrderError("amount_cents must be a positive integer")

        # Validate and normalize currency (USD only)
        currency = self._validate_currency(currency)

        # Validate request_id (required for idempotency)
        request_id = self._validate_request_id(request_id)

        # Convert cents to exact PayPal amount string (no floating point)
        amount_str = self._cents_to_amount_string(amount_cents)

        # Build order request payload
        json_data = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {
                        "currency_code": currency,
                        "value": amount_str,
                    }
                }
            ],
        }

        # Prepare headers with stable request ID for idempotency
        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "PayPal-Request-Id": request_id,
        }

        path = "/v2/checkout/orders"
        url = f"{self.base_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=json_data,
                )

                if response.status_code == 401:
                    # Token may have expired, force refresh and retry once
                    # Preserve the SAME request_id for idempotency
                    self._access_token = None
                    self._token_expires_at = 0
                    token = await self.get_access_token()
                    headers["Authorization"] = f"Bearer {token}"

                    response = await client.post(
                        url,
                        headers=headers,
                        json=json_data,
                    )

                if response.status_code >= 400:
                    error_data = response.json()
                    raise PayPalOrderError(
                        f"PayPal order creation failed ({response.status_code}): "
                        f"{error_data.get('message', error_data.get('error_description', 'Unknown error'))}"
                    )

                order_data = response.json()

                # Parse response - handle missing/malformed fields safely
                order_id = order_data.get("id")
                if not order_id:
                    raise PayPalOrderError("PayPal response missing order ID")

                status = order_data.get("status", "UNKNOWN")

                # Extract approval URL from links
                approval_url = None
                payer_id = None
                links = order_data.get("links", [])
                for link in links:
                    if link.get("rel") == "approve":
                        approval_url = link.get("href")
                    elif link.get("rel") == "payer-action":
                        # Alternative rel for approval in some API versions
                        approval_url = approval_url or link.get("href")

                create_time = order_data.get("create_time", "")
                update_time = order_data.get("update_time", "")

                return PayPalOrderResponse(
                    order_id=order_id,
                    status=status,
                    approval_url=approval_url,
                    payer_id=payer_id,
                    create_time=create_time,
                    update_time=update_time,
                    links=links,
                )

        except httpx.TimeoutException:
            raise PayPalTimeoutError(f"PayPal order creation timed out after {self.timeout}s")
        except httpx.RequestError as e:
            raise PayPalAuthenticationError(f"PayPal order request failed: {str(e)}")

    @staticmethod
    def _validate_order_id(order_id: str) -> str:
        """Validate PayPal order ID for safety.

        PayPal order IDs are alphanumeric with possible hyphens.
        Reject any that contain path separators, URL characters, or other unsafe chars.
        """
        if not order_id or not order_id.strip():
            raise PayPalCaptureError("order_id is required")
        order_id = order_id.strip()
        if len(order_id) > 64:
            raise PayPalCaptureError("order_id exceeds 64 characters")
        # PayPal order IDs: alphanumeric, hyphens, underscores only
        # Reject path separators, URL characters, and other unsafe chars
        if not re.match(r'^[A-Za-z0-9_-]+$', order_id):
            raise PayPalCaptureError("order_id contains invalid characters")
        return order_id

    @staticmethod
    def _validate_capture_request_id(request_id: str) -> str:
        """Validate PayPal-Request-Id for capture call.

        Must be non-empty, max 108 chars, no surrounding whitespace.
        """
        if not request_id or not request_id.strip():
            raise PayPalCaptureError("request_id is required for idempotency")
        request_id = request_id.strip()
        if len(request_id) > 108:
            raise PayPalCaptureError("request_id exceeds 108 characters")
        return request_id

    @staticmethod
    def _parse_amount_to_cents(value_str: str, currency_code: str) -> int:
        """Parse exact decimal string to integer cents.

        Uses Decimal for exact arithmetic, no float/round.
        Only USD is accepted.
        """
        if currency_code != "USD":
            raise PayPalCaptureError(f"Unsupported currency: {currency_code}. Only USD is supported.")
        if not value_str:
            raise PayPalCaptureError("Amount value is missing")
        try:
            # Use Decimal for exact decimal arithmetic
            decimal_value = Decimal(value_str)
        except (InvalidOperation, ValueError, TypeError):
            raise PayPalCaptureError(f"Malformed amount value: {value_str}")

        # Must be non-negative
        if decimal_value < 0:
            raise PayPalCaptureError(f"Amount must be non-negative: {value_str}")

        # Must have at most 2 decimal places (cents precision)
        if decimal_value.as_tuple().exponent < -2:
            raise PayPalCaptureError(f"Amount has too many decimal places: {value_str}")

        # Convert to cents exactly
        amount_cents = int(decimal_value * 100)
        return amount_cents

    async def capture_order(
        self,
        order_id: str,
        request_id: str,
    ) -> PayPalCaptureResponse:
        """Capture a PayPal Order v2 after buyer approval.

        This is internal plumbing only. The payment orchestration layer
        must derive the order_id from a confirmed PayPalOrder binding and
        generate a stable, separate PayPal-Request-Id for the capture call.

        Args:
            order_id: Validated PayPal order ID (from CREATED binding).
            request_id: Stable request ID for PayPal-Request-Id header
                       to support retry idempotency. Must be non-empty,
                       max 108 characters. Same ID must be used on retry.
                       Should be distinct from the create-order request ID.

        Returns:
            PayPalCaptureResponse with capture_id, capture_status, order_id,
            order_status, currency, amount_cents, and metadata.

        Raises:
            PayPalConfigurationError: If credentials not configured.
            PayPalCaptureError: If order_id/request_id validation fails
                                or PayPal API returns error.
            PayPalAuthenticationError: If authentication fails.
            PayPalTimeoutError: If request times out.

        Note:
            Does NOT automatically retry on uncertain outcomes (e.g., timeout).
            Caller must handle reconciliation manually.
        """
        # Validate order_id (must be non-empty, safe characters, reasonable length)
        order_id = self._validate_order_id(order_id)

        # Validate request_id (required for idempotency)
        request_id = self._validate_capture_request_id(request_id)

        # Prepare headers with stable request ID for idempotency
        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "PayPal-Request-Id": request_id,
        }

        path = f"/v2/checkout/orders/{order_id}/capture"
        url = f"{self.base_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json={},  # Empty body for capture
                )

                if response.status_code == 401:
                    # Token may have expired, force refresh and retry once
                    # Preserve the SAME request_id for idempotency
                    self._access_token = None
                    self._token_expires_at = 0
                    token = await self.get_access_token()
                    headers["Authorization"] = f"Bearer {token}"

                    response = await client.post(
                        url,
                        headers=headers,
                        json={},
                    )

                if response.status_code >= 400:
                    error_data = response.json()
                    raise PayPalCaptureError(
                        f"PayPal capture failed ({response.status_code}): "
                        f"{error_data.get('message', error_data.get('error_description', 'Unknown error'))}"
                    )

                capture_data = response.json()

                # Parse response according to actual PayPal Orders v2 capture structure
                #
                # Expected structure:
                # {
                #   "id": "ORDER_ID",              # Top-level is ORDER ID
                #   "status": "COMPLETED",         # Top-level is ORDER status
                #   "purchase_units": [
                #     {
                #       "payments": {
                #         "captures": [
                #           {
                #             "id": "CAPTURE_ID",  # Nested capture ID
                #             "status": "COMPLETED",
                #             "amount": {
                #               "currency_code": "USD",
                #               "value": "123.45"
                #             }
                #           }
                #         ]
                #       }
                #     }
                #   ]
                # }

                # Extract order_id from top-level id (verify it matches input)
                response_order_id = capture_data.get("id")
                if not response_order_id:
                    raise PayPalCaptureError("PayPal capture response missing order ID (top-level id)")
                if response_order_id != order_id:
                    raise PayPalCaptureError(
                        f"Order ID mismatch: requested {order_id}, got {response_order_id}"
                    )

                # Extract order_status from top-level status
                order_status = capture_data.get("status")
                if not order_status:
                    raise PayPalCaptureError("PayPal capture response missing order status")

                # Extract capture details from nested structure
                purchase_units = capture_data.get("purchase_units", [])
                if not purchase_units:
                    raise PayPalCaptureError("PayPal capture response missing purchase_units")

                # We expect exactly one purchase unit with one capture for this integration
                if len(purchase_units) != 1:
                    raise PayPalCaptureError(
                        f"Expected exactly 1 purchase_unit, got {len(purchase_units)}. "
                        f"Multiple purchase units not supported."
                    )

                purchase_unit = purchase_units[0]
                payments = purchase_unit.get("payments", {})
                captures = payments.get("captures", [])

                if not captures:
                    raise PayPalCaptureError("PayPal capture response missing captures array")

                # Reject multiple captures - fail closed
                if len(captures) != 1:
                    raise PayPalCaptureError(
                        f"Expected exactly 1 capture, got {len(captures)}. "
                        f"Multiple captures not supported; fail closed."
                    )

                capture = captures[0]

                # Extract capture_id from nested capture object
                capture_id = capture.get("id")
                if not capture_id:
                    raise PayPalCaptureError("PayPal capture response missing capture ID (nested)")

                # Extract capture_status from nested capture object
                capture_status = capture.get("status")
                if not capture_status:
                    raise PayPalCaptureError("PayPal capture response missing capture status")

                # Only treat as successful if nested capture status is COMPLETED
                if capture_status != "COMPLETED":
                    raise PayPalCaptureError(
                        f"Capture not completed: status={capture_status}. "
                        f"Only COMPLETED captures are accepted."
                    )

                # Extract amount and currency from nested capture amount
                amount_info = capture.get("amount")
                if not amount_info:
                    raise PayPalCaptureError("PayPal capture response missing amount in capture")

                currency = amount_info.get("currency_code")
                if not currency:
                    raise PayPalCaptureError("PayPal capture response missing currency_code in capture amount")

                value_str = amount_info.get("value")
                if value_str is None:
                    raise PayPalCaptureError("PayPal capture response missing value in capture amount")

                # Parse amount using exact decimal arithmetic (no float)
                amount_cents = self._parse_amount_to_cents(value_str, currency)

                # Extract timestamps and links
                create_time = capture_data.get("create_time", "")
                update_time = capture_data.get("update_time", "")
                links = capture_data.get("links", [])

                return PayPalCaptureResponse(
                    capture_id=capture_id,
                    capture_status=capture_status,
                    order_id=order_id,
                    order_status=order_status,
                    currency=currency,
                    amount_cents=amount_cents,
                    create_time=create_time,
                    update_time=update_time,
                    links=links,
                )

        except httpx.TimeoutException:
            raise PayPalTimeoutError(f"PayPal capture request timed out after {self.timeout}s")
        except httpx.RequestError as e:
            raise PayPalAuthenticationError(f"PayPal capture request failed: {str(e)}")

    async def verify_connection(self) -> bool:
        """Verify PayPal sandbox connectivity by fetching a token.

        Returns:
            True if connection successful.

        Raises:
            PayPalConfigurationError: If credentials not configured.
            PayPalAuthenticationError: If authentication fails.
            PayPalTimeoutError: If request times out.
        """
        await self.get_access_token()
        return True


# Singleton instance for application use
_paypal_client: Optional[PayPalClient] = None


def get_paypal_client() -> PayPalClient:
    """Get or create singleton PayPal client instance."""
    global _paypal_client
    if _paypal_client is None:
        _paypal_client = PayPalClient()
    return _paypal_client


def reset_paypal_client() -> None:
    """Reset singleton instance (useful for testing)."""
    global _paypal_client
    _paypal_client = None