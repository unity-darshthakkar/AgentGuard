#!/usr/bin/env python3
"""
Deterministic synthetic data seeder for AgentGuard Phase 1.

This script creates reproducible demo data for development and demonstration.
Run with: python -m backend.seed
"""

import json
import random
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.database import SessionLocal, init_db, drop_db
from app.models import (
    Agent,
    AgentStatus,
    SecurityEvent,
    SecurityEventType,
    Transaction,
    TransactionStatus,
)


# Seed for reproducibility
SEED = 42
random.seed(SEED)


# =============================================================================
# Synthetic Data Definitions
# =============================================================================

AGENTS_DATA = [
    {
        "agent_id": "AGT-2026-001",
        "name": "PaymentProcessor-Alpha",
        "description": "Primary payment processing agent for e-commerce transactions",
        "status": AgentStatus.ACTIVE,
        "owner_type": "organization",
        "owner_name": "Acme Corp",
        "owner_email": "payments@acmecorp.com",
        "owner_contact": "John Smith, VP Engineering",
        "daily_limit_usd": 50000.00,
        "monthly_limit_usd": 1000000.00,
        "allowed_merchant_categories": json.dumps(["retail", "software", "subscriptions", "utilities"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "crypto-unregulated"]),
    },
    {
        "agent_id": "AGT-2026-002",
        "name": "SubscriptionManager-Beta",
        "description": "Handles recurring subscription payments and renewals",
        "status": AgentStatus.ACTIVE,
        "owner_type": "organization",
        "owner_name": "StreamLine Inc",
        "owner_email": "billing@streamline.io",
        "owner_contact": "Sarah Chen, Finance Lead",
        "daily_limit_usd": 10000.00,
        "monthly_limit_usd": 200000.00,
        "allowed_merchant_categories": json.dumps(["subscriptions", "software", "media"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "weapons"]),
    },
    {
        "agent_id": "AGT-2026-003",
        "name": "MarketplaceBuyer-Gamma",
        "description": "Autonomous purchasing agent for marketplace procurement",
        "status": AgentStatus.ACTIVE,
        "owner_type": "human",
        "owner_name": "Alex Rivera",
        "owner_email": "alex.rivera@procurement.com",
        "owner_contact": "Direct line: +1-555-0123",
        "daily_limit_usd": 25000.00,
        "monthly_limit_usd": 500000.00,
        "allowed_merchant_categories": json.dumps(["electronics", "office-supplies", "industrial", "books"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "tobacco", "alcohol"]),
    },
    {
        "agent_id": "AGT-2026-004",
        "name": "InvoicePayer-Delta",
        "description": "Processes vendor invoices and scheduled payments",
        "status": AgentStatus.ACTIVE,
        "owner_type": "organization",
        "owner_name": "GlobalLogistics Ltd",
        "owner_email": "ap@globallogistics.com",
        "owner_contact": "Maria Santos, AP Manager",
        "daily_limit_usd": 100000.00,
        "monthly_limit_usd": 2000000.00,
        "allowed_merchant_categories": json.dumps(["logistics", "warehousing", "freight", "customs", "insurance"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "crypto-unregulated"]),
    },
    {
        "agent_id": "AGT-2026-005",
        "name": "AdSpendOptimizer-Epsilon",
        "description": "Manages advertising spend across multiple platforms",
        "status": AgentStatus.SUSPENDED,
        "owner_type": "organization",
        "owner_name": "GrowthMarketing Agency",
        "owner_email": "ads@growthmarketing.co",
        "owner_contact": "David Kim, Campaign Director",
        "daily_limit_usd": 15000.00,
        "monthly_limit_usd": 300000.00,
        "allowed_merchant_categories": json.dumps(["advertising", "social-media", "search", "display"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "political"]),
    },
    {
        "agent_id": "AGT-2026-006",
        "name": "CloudResourceManager-Zeta",
        "description": "Automates cloud infrastructure billing and scaling payments",
        "status": AgentStatus.ACTIVE,
        "owner_type": "organization",
        "owner_name": "TechStart Labs",
        "owner_email": "cloud@techstartlabs.dev",
        "owner_contact": "Priya Patel, DevOps Lead",
        "daily_limit_usd": 5000.00,
        "monthly_limit_usd": 100000.00,
        "allowed_merchant_categories": json.dumps(["cloud-hosting", "saas", "developer-tools"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "crypto-mining"]),
    },
    {
        "agent_id": "AGT-2026-007",
        "name": "TravelBooker-Eta",
        "description": "Books business travel and manages expense compliance",
        "status": AgentStatus.PENDING_REVIEW,
        "owner_type": "human",
        "owner_name": "Jordan Mitchell",
        "owner_email": "jordan.mitchell@consulting.com",
        "owner_contact": "Mobile: +1-555-0456",
        "daily_limit_usd": 5000.00,
        "monthly_limit_usd": 50000.00,
        "allowed_merchant_categories": json.dumps(["airlines", "hotels", "ground-transport", "meals"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "luxury-goods"]),
    },
    {
        "agent_id": "AGT-2026-008",
        "name": "FreelancePayer-Theta",
        "description": "Pays freelancers and contractors based on milestone completion",
        "status": AgentStatus.ACTIVE,
        "owner_type": "organization",
        "owner_name": "CreativeStudio Co",
        "owner_email": "payroll@creativestudio.design",
        "owner_contact": "Lisa Wong, Operations",
        "daily_limit_usd": 20000.00,
        "monthly_limit_usd": 400000.00,
        "allowed_merchant_categories": json.dumps(["professional-services", "design", "development", "marketing"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "weapons"]),
    },
    {
        "agent_id": "AGT-2026-009",
        "name": "DonationDistributor-Iota",
        "description": "Distributes charitable donations to verified nonprofits",
        "status": AgentStatus.ACTIVE,
        "owner_type": "organization",
        "owner_name": "GiveWell Foundation",
        "owner_email": "grants@givewell.org",
        "owner_contact": "Robert Taylor, Program Director",
        "daily_limit_usd": 25000.00,
        "monthly_limit_usd": 500000.00,
        "allowed_merchant_categories": json.dumps(["charity", "education", "healthcare", "environment"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "political", "religious"]),
    },
    {
        "agent_id": "AGT-2026-010",
        "name": "CryptoArbiter-Kappa",
        "description": "Executes approved cryptocurrency arbitrage trades",
        "status": AgentStatus.SUSPENDED,
        "owner_type": "human",
        "owner_name": "Marcus Chen",
        "owner_email": "marcus.chen@trading.fund",
        "owner_contact": "Encrypted comms only",
        "daily_limit_usd": 100000.00,
        "monthly_limit_usd": 2000000.00,
        "allowed_merchant_categories": json.dumps(["crypto-exchange", "defi", "stablecoin"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "unregulated-exchange"]),
    },
    {
        "agent_id": "AGT-2026-011",
        "name": "SupplyChainPayer-Lambda",
        "description": "Pays suppliers based on delivery confirmation and quality checks",
        "status": AgentStatus.ACTIVE,
        "owner_type": "organization",
        "owner_name": "AutoParts Manufacturing",
        "owner_email": "suppliers@autoparts-mfg.com",
        "owner_contact": "James Wilson, Supply Chain Director",
        "daily_limit_usd": 75000.00,
        "monthly_limit_usd": 1500000.00,
        "allowed_merchant_categories": json.dumps(["manufacturing", "raw-materials", "components", "quality-testing"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "luxury-goods"]),
    },
    {
        "agent_id": "AGT-2026-012",
        "name": "ResearchGrantDisburser-Mu",
        "description": "Disburses research grants to academic institutions",
        "status": AgentStatus.PENDING_REVIEW,
        "owner_type": "organization",
        "owner_name": "National Science Institute",
        "owner_email": "grants@nsi.gov",
        "owner_contact": "Dr. Amanda Foster, Grants Office",
        "daily_limit_usd": 100000.00,
        "monthly_limit_usd": 5000000.00,
        "allowed_merchant_categories": json.dumps(["education", "research", "laboratory", "publishing"]),
        "blocked_merchant_categories": json.dumps(["gambling", "adult", "political", "commercial"]),
    },
]


MERCHANTS = [
    # Retail
    ("Amazon.com", "retail", "US"),
    ("Walmart", "retail", "US"),
    ("Target", "retail", "US"),
    ("Best Buy", "electronics", "US"),
    ("Newegg", "electronics", "US"),
    # Software/SaaS
    ("AWS", "cloud-hosting", "US"),
    ("Google Cloud", "cloud-hosting", "US"),
    ("Microsoft Azure", "cloud-hosting", "US"),
    ("GitHub", "developer-tools", "US"),
    ("Atlassian", "software", "AU"),
    ("Slack", "software", "US"),
    ("Notion", "software", "US"),
    ("Figma", "design", "US"),
    # Subscriptions
    ("Netflix", "media", "US"),
    ("Spotify", "media", "SE"),
    ("Adobe Creative Cloud", "software", "US"),
    ("Microsoft 365", "software", "US"),
    # Advertising
    ("Google Ads", "advertising", "US"),
    ("Meta Ads", "advertising", "US"),
    ("LinkedIn Ads", "advertising", "US"),
    ("TikTok Ads", "advertising", "CN"),
    # Professional Services
    ("Upwork", "professional-services", "US"),
    ("Fiverr", "professional-services", "IL"),
    ("Toptal", "professional-services", "US"),
    # Travel
    ("Delta Airlines", "airlines", "US"),
    ("United Airlines", "airlines", "US"),
    ("Marriott Hotels", "hotels", "US"),
    ("Hilton Hotels", "hotels", "US"),
    ("Uber", "ground-transport", "US"),
    # Logistics
    ("FedEx", "logistics", "US"),
    ("UPS", "logistics", "US"),
    ("DHL", "logistics", "DE"),
    # Manufacturing
    ("DigiKey", "components", "US"),
    ("Mouser Electronics", "components", "US"),
    ("McMaster-Carr", "industrial", "US"),
    # Charity
    ("Red Cross", "charity", "US"),
    ("UNICEF", "charity", "US"),
    ("Doctors Without Borders", "charity", "CH"),
    # Crypto
    ("Coinbase", "crypto-exchange", "US"),
    ("Binance", "crypto-exchange", "KY"),
    ("Kraken", "crypto-exchange", "US"),
    # Utilities
    ("Stripe", "payments", "US"),
    ("Plaid", "fintech", "US"),
    ("Twilio", "developer-tools", "US"),
    # Education/Research
    ("MIT Press", "publishing", "US"),
    ("IEEE", "research", "US"),
    ("Elsevier", "publishing", "NL"),
]

TRANSACTION_STATUSES = [
    TransactionStatus.APPROVED,
    TransactionStatus.BLOCKED,
    TransactionStatus.UNDER_REVIEW,
]

# Weighted distribution for realistic demo data
STATUS_WEIGHTS = [0.6, 0.2, 0.2]  # 60% approved, 20% blocked, 20% under review

RISK_LEVELS = [
    (0, 30, "low"),
    (31, 60, "medium"),
    (61, 85, "high"),
    (86, 100, "critical"),
]

DECISION_REASONS = {
    TransactionStatus.APPROVED: [
        "Transaction within approved limits and normal patterns",
        "Verified merchant, amount within daily limit",
        "Recurring payment to approved vendor",
        "Standard procurement transaction",
        "Approved subscription renewal",
    ],
    TransactionStatus.BLOCKED: [
        "Exceeds daily spending limit",
        "Merchant category not in allowed list",
        "Risk score exceeds threshold (>= 85)",
        "Geo-anomaly: transaction from high-risk country",
        "Velocity anomaly: too many transactions in short period",
        "Amount outlier: 3x standard deviation from mean",
        "New merchant not in approved vendor list",
        "Permission violation: blocked category",
    ],
    TransactionStatus.UNDER_REVIEW: [
        "Elevated risk score requires manual review",
        "New merchant category for this agent",
        "Unusual transaction amount for this agent",
        "Geographic anomaly detected",
        "Velocity spike requires verification",
        "Pattern deviation from historical behavior",
    ],
}

SECURITY_EVENT_TEMPLATES = [
    (SecurityEventType.VELOCITY_ANOMALY, "warning", "Velocity Anomaly Detected",
     "Agent made {count} transactions in {minutes} minutes, exceeding normal rate"),
    (SecurityEventType.GEO_ANOMALY, "warning", "Geographic Anomaly",
     "Transaction from {country} unusual for agent (typical: {typical_countries})"),
    (SecurityEventType.AMOUNT_OUTLIER, "warning", "Amount Outlier",
     "Transaction amount ${amount} is {deviation}x standard deviation from agent mean"),
    (SecurityEventType.NEW_MERCHANT, "info", "New Merchant",
     "First transaction with {merchant} (category: {category})"),
    (SecurityEventType.PERMISSION_VIOLATION, "critical", "Permission Violation",
     "Transaction to blocked category {category} rejected"),
    (SecurityEventType.PATTERN_DEVIATION, "warning", "Pattern Deviation",
     "Transaction pattern deviates from historical baseline (score: {score})"),
]


def get_risk_level(score: int) -> str:
    """Determine risk level from score."""
    for min_score, max_score, level in RISK_LEVELS:
        if min_score <= score <= max_score:
            return level
    return "low"


def generate_transactions(db, agents: list[Agent]) -> list[Transaction]:
    """Generate synthetic transactions for agents."""
    transactions = []
    transaction_id_counter = 1

    # Generate transactions over the last 30 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)

    for agent in agents:
        # Each agent gets 5-10 transactions
        num_txns = random.randint(5, 10)

        for _ in range(num_txns):
            # Random timestamp within range
            txn_time = start_date + timedelta(
                seconds=random.randint(0, int((end_date - start_date).total_seconds()))
            )

            # Pick random merchant
            merchant_name, merchant_category, merchant_country = random.choice(MERCHANTS)

            # Generate amount based on agent's daily limit
            max_amount = float(agent.daily_limit_usd) * 0.5
            amount = round(random.uniform(10.0, max_amount), 2)

            # Determine status (weighted)
            status = random.choices(TRANSACTION_STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

            # Generate risk score based on status
            if status == TransactionStatus.APPROVED:
                risk_score = random.randint(0, 40)
            elif status == TransactionStatus.BLOCKED:
                risk_score = random.randint(60, 95)
            else:  # UNDER_REVIEW
                risk_score = random.randint(40, 80)

            risk_level = get_risk_level(risk_score)
            decision_reason = random.choice(DECISION_REASONS[status])

            # Set decided/completed times
            decided_at = txn_time + timedelta(minutes=random.randint(1, 60))
            completed_at = decided_at + timedelta(minutes=random.randint(1, 30)) if status == TransactionStatus.APPROVED else None

            txn = Transaction(
                transaction_id=f"TXN-{SEED:04d}-{transaction_id_counter:06d}",
                agent_id=agent.id,
                amount_usd=Decimal(str(amount)),
                currency="USD",
                merchant_name=merchant_name,
                merchant_category=merchant_category,
                merchant_country=merchant_country,
                description=f"Auto-generated demo transaction for {agent.name}",
                status=status,
                risk_score=risk_score,
                risk_level=risk_level,
                decision_reason=decision_reason,
                requested_at=txn_time,
                decided_at=decided_at,
                completed_at=completed_at,
            )
            transactions.append(txn)
            transaction_id_counter += 1

    # Sort by requested_at for realistic ordering
    transactions.sort(key=lambda t: t.requested_at)
    return transactions


def generate_security_events(db, agents: list[Agent], transactions: list[Transaction]) -> list[SecurityEvent]:
    """Generate synthetic security events."""
    events = []
    event_id_counter = 1

    # Map transactions by agent for easier lookup
    txns_by_agent = {}
    for txn in transactions:
        if txn.agent_id not in txns_by_agent:
            txns_by_agent[txn.agent_id] = []
        txns_by_agent[txn.agent_id].append(txn)

    for agent in agents:
        agent_txns = txns_by_agent.get(agent.id, [])
        num_events = random.randint(1, 5)

        for _ in range(num_events):
            # Pick a random transaction or None for agent-level events
            txn = random.choice(agent_txns) if agent_txns and random.random() > 0.3 else None

            template = random.choice(SECURITY_EVENT_TEMPLATES)
            event_type, severity, title_template, desc_template = template

            # Generate contextual details
            if txn:
                merchant = txn.merchant_name
                category = txn.merchant_category
                amount = txn.amount_usd
                country = txn.merchant_country
            else:
                merchant = random.choice(MERCHANTS)[0]
                category = random.choice(MERCHANTS)[1]
                amount = round(random.uniform(100, 5000), 2)
                country = random.choice(MERCHANTS)[2]

            typical_countries = ["US", "CA", "GB", "DE"]
            typical_countries = [c for c in typical_countries if c != country]

            details = {
                "merchant": merchant,
                "category": category,
                "amount": float(amount),
                "country": country,
                "agent_id": agent.agent_id,
            }

            if event_type == SecurityEventType.VELOCITY_ANOMALY:
                details.update({"count": random.randint(5, 20), "minutes": random.randint(5, 30)})
            elif event_type == SecurityEventType.AMOUNT_OUTLIER:
                details.update({"deviation": round(random.uniform(2.5, 5.0), 1)})
            elif event_type == SecurityEventType.PATTERN_DEVIATION:
                details.update({"score": random.randint(60, 90)})

            description = desc_template.format(
                count=details.get("count", 0),
                minutes=details.get("minutes", 0),
                country=country,
                typical_countries=", ".join(typical_countries[:3]),
                amount=details.get("amount", 0),
                deviation=details.get("deviation", 0),
                merchant=merchant,
                category=category,
                score=details.get("score", 0),
            )

            detected_at = txn.requested_at + timedelta(minutes=random.randint(0, 10)) if txn else datetime.utcnow() - timedelta(hours=random.randint(1, 72))

            # Some events acknowledged, some not
            acknowledged_at = None
            acknowledged_by = None
            if random.random() > 0.4:
                acknowledged_at = detected_at + timedelta(hours=random.randint(1, 24))
                acknowledged_by = random.choice(["Security Analyst", "Auto-Resolved", "Admin User"])

            event = SecurityEvent(
                event_id=f"EVT-{SEED:04d}-{event_id_counter:06d}",
                agent_id=agent.id,
                transaction_id=txn.id if txn else None,
                event_type=event_type,
                severity=severity,
                title=title_template,
                description=description,
                details_json=json.dumps(details),
                detected_at=detected_at,
                acknowledged_at=acknowledged_at,
                acknowledged_by=acknowledged_by,
            )
            events.append(event)
            event_id_counter += 1

    return events


def seed_database() -> None:
    """Seed the database with deterministic synthetic data."""
    print("[SEED] Starting database seeding...")
    print(f"   Using seed: {SEED}")

    # Initialize database
    init_db()

    # Drop and recreate for idempotency
    print("   Dropping existing tables...")
    drop_db()
    print("   Creating tables...")
    init_db()

    db = SessionLocal()
    try:
        # Create agents
        print("   Creating agents...")
        agents = []
        for i, agent_data in enumerate(AGENTS_DATA):
            agent = Agent(
                **agent_data,
                created_at=datetime.utcnow() - timedelta(days=random.randint(30, 365)),
                updated_at=datetime.utcnow() - timedelta(days=random.randint(0, 30)),
                last_active_at=datetime.utcnow() - timedelta(hours=random.randint(1, 72)) if agent_data["status"] == AgentStatus.ACTIVE else None,
            )
            db.add(agent)
            agents.append(agent)

        db.flush()  # Get IDs

        # Create transactions
        print("   Creating transactions...")
        transactions = generate_transactions(db, agents)
        for txn in transactions:
            db.add(txn)

        db.flush()  # Get transaction IDs

        # Create security events
        print("   Creating security events...")
        events = generate_security_events(db, agents, transactions)
        for event in events:
            db.add(event)

        db.commit()

        print("[SEED] Seeding complete!")
        print(f"   Agents: {len(agents)}")
        print(f"   Transactions: {len(transactions)}")
        print(f"   Security Events: {len(events)}")
        print()
        print("[SEED] NOTE: All data is SYNTHETIC DEMONSTRATION DATA for Phase 1.")
        print("   No real agent authentication, AI detection, or PayPal integration.")

    except Exception as e:
        db.rollback()
        print(f"[SEED] Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()