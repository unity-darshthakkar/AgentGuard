#!/usr/bin/env python3
"""
PayPal Sandbox End-to-End Verification Script

This script performs a complete sandbox checkout flow:
1. Creates/uses an existing ALLOW authorization decision with RESERVED reservation
2. Calls POST /api/checkout/start to create a PayPal order
3. Prints the PayPal Sandbox approval URL for buyer approval
4. Waits for buyer to approve in sandbox
5. Calls POST /api/checkout/{id}/capture to capture the order
6. Retrieves checkout status and verifies final state

Usage:
    python sandbox_e2e_verify.py                          # Interactive mode
    python sandbox_e2e_verify.py --dry-run                # Validate config only
    python sandbox_e2e_verify.py --reuse-existing         # Reuse existing auth decision
    python sandbox_e2e_verify.py --auth-decision-id 123   # Use specific auth decision
    python sandbox_e2e_verify.py --base-url http://localhost:8000/api

Requirements:
    - .env file with PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, ADMIN_API_KEY
    - PayPal sandbox buyer account for approval
    - Backend server running (uvicorn app.main:app --reload)
"""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv


def load_env_files():
    """Load environment variables from .env files (root first, then backend).
    Must be called BEFORE importing app.core.config to ensure Pydantic Settings
    picks up the environment variables.
    Uses python-dotenv for proper .env parsing.
    """
    loaded = False

    # Check root .env first (project root)
    root_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(root_env):
        load_dotenv(root_env, override=False)
        print(f"[OK] Loaded environment from: {root_env}")
        loaded = True

    # Also check backend/.env (for backwards compatibility)
    backend_env = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(backend_env):
        load_dotenv(backend_env, override=False)
        print(f"[OK] Loaded environment from: {backend_env}")
        loaded = True

    if not loaded:
        print("[ERROR] No .env file found. Checked:")
        print(f"   - {root_env}")
        print(f"   - {backend_env}")
        print("   Copy .env.example to .env and fill in your values.")

    return loaded


# Load environment FIRST before importing config
load_env_files()

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import get_settings
from app.core.database import get_db, init_db
from app.models import (
    Agent,
    AgentCredential,
    AuthorizationDecision,
    AuthorizationDecisionRecord,
    AuthorizationReservation,
    CredentialStatus,
    DailyBudgetUsage,
    PolicyStatus,
    ReservationStatus,
    SpendingPolicy,
)
from app.services import (
    register_agent_credential,
    create_spending_policy,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def check_credentials():
    """Verify required environment variables are set."""
    settings = get_settings()
    missing = []

    if not settings.paypal_client_id:
        missing.append("PAYPAL_CLIENT_ID")
    if not settings.paypal_client_secret:
        missing.append("PAYPAL_CLIENT_SECRET")
    if not settings.admin_api_key:
        missing.append("ADMIN_API_KEY")

    if missing:
        print(f"[ERROR] Missing required environment variables: {', '.join(missing)}")
        print("   Set them in your .env file")
        return False

    print("[OK] Environment variables configured")
    # Mask credentials completely - don't print even partial values
    print(f"   PAYPAL_CLIENT_ID: *** (configured)")
    print(f"   ADMIN_API_KEY: *** (configured)")
    return True


def find_existing_auth_decision(db: Session) -> Optional[AuthorizationDecisionRecord]:
    """Find an existing ALLOW decision with RESERVED reservation and CREATED PayPal order."""
    # Find ALLOW decisions with RESERVED reservations
    auth_decision = db.query(AuthorizationDecisionRecord).join(
        AuthorizationReservation,
        AuthorizationReservation.auth_decision_id == AuthorizationDecisionRecord.id
    ).filter(
        AuthorizationDecisionRecord.decision == AuthorizationDecision.ALLOW,
        AuthorizationReservation.status == ReservationStatus.RESERVED
    ).first()

    if auth_decision:
        # Verify it has a PayPal order in CREATED status
        from app.models import PayPalOrder, PayPalOrderStatus
        paypal_order = db.query(PayPalOrder).filter(
            PayPalOrder.auth_decision_id == auth_decision.id,
            PayPalOrder.status == PayPalOrderStatus.CREATED
        ).first()

        if paypal_order and paypal_order.approval_url:
            return auth_decision

    return None


def create_test_data(db: Session, unique_suffix: str) -> AuthorizationDecisionRecord:
    """Create a test agent, policy, authorization decision, and reservation."""
    print("\n[CREATE] Creating test authorization decision...")

    # Create agent with unique identifier
    agent_id = f"sandbox-test-agent-{unique_suffix}"
    agent = Agent(
        agent_id=agent_id,
        name=f"Sandbox Test Agent {unique_suffix}",
        description="Agent for sandbox E2E verification",
        owner_type="human",
        owner_name="Test Owner",
        owner_email="test@example.com",
        daily_limit_usd=1000.00,
        monthly_limit_usd=10000.00,
    )
    db.add(agent)
    db.flush()

    # Create credential
    credential = register_agent_credential(
        db=db,
        agent=agent,
        public_key_pem="""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA7QVWw1Yg6aOaJQYF5ZxY8Q3Lq8JbK2Vh8N6mQ9R7U0c=
-----END PUBLIC KEY-----""",
        expires_in_days=365,
    )

    # Create spending policy
    policy = create_spending_policy(
        db=db,
        agent=agent,
        owner_id="human:test@example.com",
        per_transaction_limit_cents=50000,
        daily_budget_cents=100000,
        allowed_currencies=["USD"],
        expires_in_days=365,
    )

    # Create authorization decision (ALLOW)
    auth_decision = AuthorizationDecisionRecord(
        request_id=f"req-sandbox-e2e-{unique_suffix}",
        idempotency_key=f"idem-sandbox-e2e-{unique_suffix}",
        agent_id=agent.id,
        credential_id=credential.id,
        policy_id=policy.id,
        amount_cents=2500,  # $25.00
        currency="USD",
        merchant_id="sandbox-merchant-001",
        merchant_category="retail",
        description="Sandbox E2E test purchase",
        decision=AuthorizationDecision.ALLOW,
        reasons='["Within policy limits"]',
        policy_violations=None,
        daily_spent_before_cents=0,
        daily_spent_after_cents=2500,
    )
    db.add(auth_decision)
    db.flush()

    # Create reservation
    usage_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    reservation = AuthorizationReservation(
        auth_decision_id=auth_decision.id,
        agent_id=agent.id,
        policy_id=policy.id,
        amount_cents=2500,
        currency="USD",
        usage_date=usage_date,
        status=ReservationStatus.RESERVED,
    )
    db.add(reservation)
    db.flush()

    # Create budget record
    budget = DailyBudgetUsage(
        agent_id=agent.id,
        usage_date=usage_date,
        daily_budget_cents=100000,
        reserved_cents=2500,
        captured_cents=0,
    )
    db.add(budget)
    db.commit()
    db.refresh(auth_decision)
    db.refresh(reservation)

    print(f"[OK] Created authorization decision: {auth_decision.id}")
    print(f"   Amount: ${auth_decision.amount_cents / 100:.2f} {auth_decision.currency}")
    print(f"   Reservation: {reservation.id} (status: {reservation.status.value})")
    return auth_decision


def get_auth_headers():
    """Get admin authentication headers."""
    settings = get_settings()
    return {"X-Admin-API-Key": settings.admin_api_key}


def start_checkout(base_url: str, auth_decision_id: int) -> dict:
    """Call POST /api/checkout/start."""
    print(f"\n[START] Starting checkout for authorization decision {auth_decision_id}...")
    response = httpx.post(
        f"{base_url}/checkout/start",
        json={"authorization_decision_id": auth_decision_id},
        headers=get_auth_headers(),
        timeout=30.0,
    )

    if response.status_code != 200:
        print(f"[ERROR] Checkout start failed: {response.status_code}")
        print(f"   {response.text}")
        sys.exit(1)

    data = response.json()
    print("[OK] Checkout started successfully")
    print(f"   PayPal Order ID: {data['paypal_order_id']}")
    print(f"   Approval URL: {data['approval_url']}")
    print(f"   Checkout Status: {data['checkout_status']}")
    print(f"   Reservation Status: {data['reservation_status']}")
    return data


def wait_for_approval(approval_url: str, dry_run: bool = False):
    """Wait for user to approve in PayPal sandbox."""
    if dry_run:
        print("\n[DRY RUN] Skipping manual approval step")
        return

    print("=" * 70)
    print("[MANUAL] MANUAL ACTION REQUIRED")
    print("=" * 70)
    print("1. Open the following URL in a browser:")
    print(f"   {approval_url}")
    print("2. Log in with your PayPal SANDBOX BUYER account")
    print("   (NOT your personal/facilitator account - use a sandbox buyer)")
    print("3. Approve the payment")
    print("4. Return here and press ENTER to continue...")
    print("=" * 70)
    print("[WARNING] IMPORTANT: Use a PayPal Sandbox BUYER account, not the facilitator!")
    print("   Create one at: https://developer.paypal.com/dashboard/accounts")
    print("=" * 70)
    input("\nPress ENTER after buyer approval... ")


def capture_checkout(base_url: str, auth_decision_id: int, dry_run: bool = False) -> dict:
    """Call POST /api/checkout/{id}/capture."""
    if dry_run:
        print("\n[DRY RUN] Skipping capture step")
        return {"paypal_order_id": "DRY_RUN", "paypal_capture_id": "DRY_RUN",
                "capture_status": "completed", "reservation_status": "captured",
                "reconciliation_required": False, "reconciliation_reason": None}

    print(f"\n[CAPTURE] Capturing payment for authorization decision {auth_decision_id}...")
    response = httpx.post(
        f"{base_url}/checkout/{auth_decision_id}/capture",
        headers=get_auth_headers(),
        timeout=30.0,
    )

    if response.status_code != 200:
        print(f"[ERROR] Capture failed: {response.status_code}")
        print(f"   {response.text}")
        sys.exit(1)

    data = response.json()
    print("[OK] Capture successful")
    print(f"   PayPal Order ID: {data['paypal_order_id']}")
    print(f"   PayPal Capture ID: {data['paypal_capture_id']}")
    print(f"   Capture Status: {data['capture_status']}")
    print(f"   Reservation Status: {data['reservation_status']}")
    print(f"   Reconciliation Required: {data['reconciliation_required']}")
    if data['reconciliation_reason']:
        print(f"   Reconciliation Reason: {data['reconciliation_reason']}")
    return data


def get_checkout_status(base_url: str, auth_decision_id: int, dry_run: bool = False) -> dict:
    """Call GET /api/checkout/{id}."""
    if dry_run:
        print("\n[DRY RUN] Skipping status fetch")
        return {"decision": "allow", "amount_cents": 2500, "currency": "USD",
                "reservation_status": "captured", "paypal_order_status": "created",
                "paypal_capture_status": "completed", "paypal_capture_id": "DRY_RUN",
                "reconciliation_required": False, "reconciliation_reason": None,
                "decided_at": datetime.now().isoformat(), "reserved_at": datetime.now().isoformat(),
                "captured_at": datetime.now().isoformat()}

    print(f"\n[STATUS] Fetching checkout status for authorization decision {auth_decision_id}...")
    response = httpx.get(
        f"{base_url}/checkout/{auth_decision_id}",
        headers=get_auth_headers(),
        timeout=10.0,
    )

    if response.status_code != 200:
        print(f"[ERROR] Status fetch failed: {response.status_code}")
        print(f"   {response.text}")
        sys.exit(1)

    data = response.json()
    print("[OK] Status retrieved")
    print(f"   Decision: {data['decision']}")
    print(f"   Amount: ${data['amount_cents'] / 100:.2f} {data['currency']}")
    print(f"   Reservation Status: {data['reservation_status']}")
    print(f"   PayPal Order Status: {data['paypal_order_status']}")
    print(f"   PayPal Capture Status: {data['paypal_capture_status']}")
    print(f"   PayPal Capture ID: {data['paypal_capture_id']}")
    print(f"   Reconciliation Required: {data['reconciliation_required']}")
    if data['reconciliation_reason']:
        print(f"   Reconciliation Reason: {data['reconciliation_reason']}")
    print(f"   Decided At: {data['decided_at']}")
    print(f"   Reserved At: {data['reserved_at']}")
    print(f"   Captured At: {data['captured_at']}")
    return data


def verify_final_state(status: dict) -> bool:
    """Verify the final state matches expectations."""
    print("\n" + "=" * 70)
    print("[VERIFY] VERIFICATION")
    print("=" * 70)

    checks = [
        ("Decision is ALLOW", status["decision"] == "allow"),
        ("Reservation is CAPTURED", status["reservation_status"] == "captured"),
        ("PayPal order is CREATED", status["paypal_order_status"] == "created"),
        ("PayPal capture is COMPLETED", status["paypal_capture_status"] == "completed"),
        ("Has PayPal capture ID", bool(status["paypal_capture_id"])),
        ("No reconciliation required", not status["reconciliation_required"]),
        ("Captured timestamp exists", bool(status["captured_at"])),
    ]

    all_passed = True
    for name, result in checks:
        status_icon = "[OK]" if result else "[FAIL]"
        print(f"   {status_icon} {name}")
        if not result:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("[SUCCESS] ALL CHECKS PASSED - Sandbox E2E verification successful!")
    else:
        print("[WARNING] SOME CHECKS FAILED - Review the output above")
    print("=" * 70)

    return all_passed


async def main():
    """Main verification flow."""
    parser = argparse.ArgumentParser(
        description="PayPal Sandbox E2E Verification for AgentGuard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sandbox_e2e_verify.py                          # Full interactive flow
  python sandbox_e2e_verify.py --dry-run                # Validate config only
  python sandbox_e2e_verify.py --reuse-existing         # Reuse existing ALLOW decision
  python sandbox_e2e_verify.py --auth-decision-id 42    # Use specific decision ID
  python sandbox_e2e_verify.py --base-url http://x:8000 # Custom API base URL
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without making real API calls"
    )
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reuse existing ALLOW decision with RESERVED reservation and CREATED PayPal order"
    )
    parser.add_argument(
        "--auth-decision-id",
        type=int,
        help="Use specific authorization decision ID (skips creation/reuse logic)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8001/api",
        help="API base URL (default: http://localhost:8001/api)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("[TEST] AgentGuard PayPal Sandbox E2E Verification")
    print("=" * 70)

    if args.dry_run:
        print("[DRY RUN] No real API calls will be made")
        print("=" * 70)

    # Verify credentials
    if not check_credentials():
        return 1

    # Initialize database
    print("\n[INIT] Initializing database...")
    init_db()

    if args.dry_run:
        print("[DRY RUN] Configuration validated successfully!")
        print("   Environment variables: OK")
        print("   Database connection: OK")
        print("   All imports: OK")
        return 0

    # Get database session
    db = next(get_db())

    try:
        auth_decision = None

        if args.auth_decision_id:
            # Use specific auth decision ID
            auth_decision = db.query(AuthorizationDecisionRecord).filter(
                AuthorizationDecisionRecord.id == args.auth_decision_id
            ).first()
            if not auth_decision:
                print(f"[ERROR] Authorization decision {args.auth_decision_id} not found")
                return 1
            print(f"[OK] Using specified authorization decision: {auth_decision.id}")

        elif args.reuse_existing:
            # Try to find existing suitable auth decision
            print("\n[SEARCH] Searching for existing ALLOW decision with RESERVED reservation...")
            auth_decision = find_existing_auth_decision(db)
            if auth_decision:
                print(f"[OK] Found existing authorization decision: {auth_decision.id}")
                print(f"   Amount: ${auth_decision.amount_cents / 100:.2f} {auth_decision.currency}")
            else:
                print("[WARNING] No suitable existing decision found, creating new one...")
                unique_suffix = uuid.uuid4().hex[:8]
                auth_decision = create_test_data(db, unique_suffix)
        else:
            # Create new test data
            unique_suffix = uuid.uuid4().hex[:8]
            auth_decision = create_test_data(db, unique_suffix)

        # Step 1: Start checkout
        checkout_data = start_checkout(args.base_url, auth_decision.id)
        approval_url = checkout_data["approval_url"]

        if not approval_url:
            print("[ERROR] No approval URL returned")
            return 1

        # Step 2: Wait for buyer approval
        wait_for_approval(approval_url, dry_run=args.dry_run)

        # Step 3: Capture payment
        capture_data = capture_checkout(args.base_url, auth_decision.id, dry_run=args.dry_run)

        # Step 4: Get final status
        status_data = get_checkout_status(args.base_url, auth_decision.id, dry_run=args.dry_run)

        # Step 5: Verify final state
        success = verify_final_state(status_data)

        return 0 if success else 1

    finally:
        db.close()


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n[WARNING] Verification interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)