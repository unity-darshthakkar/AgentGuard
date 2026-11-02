# AgentGuard Architecture

## Overview

AgentGuard is a zero-trust security gateway for autonomous AI agents making payments through PayPal. This document describes the Phase 1 architecture, which provides a demonstration dashboard with synthetic data.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentGuard System                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐       ┌──────────────┐       ┌────────────┐  │
│  │   Frontend   │◄─────►│    Backend   │◄─────►│  Database  │  │
│  │  (React 18)  │       │  (FastAPI)   │       │  (SQLite)  │  │
│  │              │       │              │       │            │  │
│  │ • Dashboard  │       │ • REST API   │       │ • Agents   │  │
│  │ • AG Grid    │       │ • Services   │       │ • Txns     │  │
│  │ • Tailwind   │       │ • Models     │       │ • Events   │  │
│  └──────────────┘       └──────────────┘       └────────────┘  │
│         │                       │                      ▲        │
│         │                       │                      │        │
│         ▼                       ▼                      │        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Vite Dev Proxy                         │   │
│  │              (Frontend :5173 → Backend :8000)             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

### Backend
- **Framework**: FastAPI 0.109+
- **ORM**: SQLAlchemy 2.0 (async)
- **Validation**: Pydantic v2
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Testing**: pytest + pytest-asyncio
- **Server**: Uvicorn

### Frontend
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite 5
- **Styling**: Tailwind CSS
- **Data Grid**: AG Grid Community
- **HTTP Client**: Axios
- **Date Handling**: date-fns
- **Icons**: Lucide React
- **Testing**: Vitest

## Data Model

### Agent
| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| agent_id | String | Unique agent identifier (AGT-XXXX-XXX) |
| name | String | Display name |
| description | Text | Agent description |
| status | Enum | active, suspended, pending_review, decommissioned |
| owner_type | Enum | human, organization |
| owner_name | String | Owner name |
| owner_email | String | Owner email |
| owner_contact | String | Contact info |
| daily_limit_usd | Float | Daily spending limit |
| monthly_limit_usd | Float | Monthly spending limit |
| allowed_merchant_categories | JSON | Allowed categories array |
| blocked_merchant_categories | JSON | Blocked categories array |
| created_at | DateTime | Creation timestamp |
| updated_at | DateTime | Last update timestamp |
| last_active_at | DateTime | Last activity timestamp |

### Transaction
| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| transaction_id | String | Unique transaction ID (TXN-XXXX-XXXXX) |
| agent_id | Integer | FK to Agent |
| amount_usd | Float | Transaction amount |
| currency | String | Currency code (default USD) |
| merchant_name | String | Merchant name |
| merchant_category | String | Merchant category |
| merchant_country | String | ISO country code |
| description | Text | Transaction description |
| status | Enum | approved, blocked, under_review, pending, failed |
| risk_score | Integer | Risk score 0-100 |
| risk_level | Enum | low, medium, high, critical |
| decision_reason | Text | Decision explanation |
| requested_at | DateTime | Request timestamp |
| decided_at | DateTime | Decision timestamp |
| completed_at | DateTime | Completion timestamp |

### SecurityEvent
| Field | Type | Description |
|-------|------|-------------|
| id | Integer | Primary key |
| event_id | String | Unique event ID (EVT-XXXX-XXXXX) |
| agent_id | Integer | FK to Agent (nullable) |
| event_type | Enum | velocity_anomaly, geo_anomaly, pattern_deviation, limit_breach, unauthorized_merchant, suspicious_pattern |
| severity | Enum | info, warning, critical |
| description | Text | Event description |
| details | JSON | Additional event details |
| acknowledged | Boolean | Acknowledgment status |
| acknowledged_at | DateTime | Acknowledgment timestamp |
| detected_at | DateTime | Detection timestamp |

## API Endpoints

### Health
- `GET /api/health` - Health check

### Agents
- `GET /api/agents` - List agents (paginated, filtered, sorted)
- `GET /api/agents/{agent_id}` - Get agent detail

### Transactions
- `GET /api/transactions` - List transactions (paginated, filtered, sorted)
- `GET /api/transactions/{transaction_id}` - Get transaction detail

### Security Events
- `GET /api/security-events` - List security events (paginated, filtered, sorted)

### Dashboard
- `GET /api/dashboard/summary` - KPI summary

## Security Considerations (Phase 1)

- **CORS**: Restricted to configured origins (localhost:5173)
- **SQL Injection**: Prevented via SQLAlchemy ORM
- **Input Validation**: Pydantic schemas on all endpoints
- **Rate Limiting**: Not implemented in Phase 1 (planned for Phase 2)
- **Authentication**: Not implemented in Phase 1 (planned for Phase 2)
- **Authorization**: Display-only permissions in Phase 1

## Deployment

### Development
```bash
# Backend
cd backend
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python -m uvicorn app.main:app --reload

# Frontend
cd frontend
npm run dev
```

### Production (Future)
- Backend: Docker + PostgreSQL + Gunicorn/Uvicorn workers
- Frontend: Static build served via nginx/CDN
- Database: PostgreSQL with connection pooling
- Monitoring: Prometheus + Grafana

## Synthetic Data

All data in Phase 1 is **synthetic demonstration data**:
- 12 agents with varied statuses and limits
- 91 transactions with realistic risk scores
- 35 security events of varying severity
- Generated deterministically via `python seed.py`

## Future Extensions (Phase 2+)

- Real PayPal API integration
- ML-based risk scoring
- Real-time WebSocket updates
- Authentication (OAuth2/OIDC)
- Role-based access control
- Audit logging
- Webhook notifications
- PostgreSQL support