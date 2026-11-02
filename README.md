# AgentGuard

**Zero-trust security gateway for autonomous AI agents making payments through PayPal**

AgentGuard verifies agent identities, checks delegated spending permissions, detects suspicious transaction behavior, and prevents unauthorized payment execution. An AG Grid security operations dashboard gives organizations visibility into agent activity and payment decisions.

> **⚠️ Phase 1 Status**: This is a **synthetic demonstration** with mock data. No real agent authentication, AI anomaly detection, or PayPal payment execution is implemented. All data is seeded for demonstration purposes only.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AgentGuard                               │
├──────────────────────┬──────────────────────────────────────────┤
│     Frontend         │              Backend                     │
│  (React + TypeScript)│           (FastAPI + Python)             │
│  Port: 5173          │           Port: 8000                     │
│                      │                                          │
│  - AG Grid tables    │  - REST API (/api/*)                     │
│  - KPI Dashboard     │  - SQLAlchemy ORM                        │
│  - Transaction detail│  - SQLite (dev) / PostgreSQL (prod)      │
│  - Polling updates   │  - Pydantic validation                   │
└──────────────────────┴──────────────────────────────────────────┘
```

---

## Quick Start (PowerShell)

### Prerequisites
- **Python 3.11+** (tested with 3.14)
- **Node.js 18+** (tested with 22.x)
- **npm 9+** (tested with 10.x)

### 1. Clone and Navigate
```powershell
cd C:\Users\5dars\Desktop\Paypal
```

### 2. Backend Setup
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r backend/requirements.txt

# Copy environment file
Copy-Item .env.example .env

# Seed database with synthetic data
python -m backend.seed

# Start backend server
python -m backend.main
```
Backend runs at: **http://localhost:8000**  
API docs at: **http://localhost:8000/docs**

### 3. Frontend Setup (New Terminal)
```powershell
cd C:\Users\5dars\Desktop\Paypal

# Install dependencies
cd frontend
npm install

# Start development server
npm run dev
```
Frontend runs at: **http://localhost:5173**

### Local admin authentication

The backend reads the repository-root `.env` automatically, regardless of whether it is started from the repository root or `backend`. Keep `ADMIN_API_KEY` only in that file or the process environment; process environment variables take precedence.

Start the services without `--env-file` or frontend key variables:

```powershell
# Terminal 1
cd C:\Users\5dars\Desktop\Paypal\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2
cd C:\Users\5dars\Desktop\Paypal\frontend
npm run dev
```

In local Vite development, the server-side proxy reads `ADMIN_API_KEY` from the root `.env` and adds it only to proxied backend requests. It is not part of the browser bundle. Direct API calls still require the existing `X-Admin-API-Key` header. The Attack Simulator uses an in-memory database and never creates PayPal orders or captures.

---

## Project Structure

```
agentguard/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI routes
│   │   ├── models/        # SQLAlchemy models
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic
│   │   ├── core/          # Config, database
│   │   └── main.py        # App entry point
│   ├── seed.py            # Synthetic data seeder
│   ├── tests/             # pytest tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── pages/         # Page components
│   │   ├── hooks/         # Custom hooks
│   │   ├── services/      # API client
│   │   ├── types/         # TypeScript types
│   │   └── utils/         # Helpers
│   ├── tests/             # Vitest tests
│   ├── package.json
│   └── vite.config.ts
├── docs/
│   ├── architecture.md
│   └── roadmap.md
├── .gitignore
├── .env.example
└── README.md
```

---

## API Endpoints (Phase 1)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/agents` | List all agents (paginated) |
| GET | `/api/agents/{id}` | Get agent details |
| GET | `/api/transactions` | List transactions (paginated, filterable) |
| GET | `/api/transactions/{id}` | Get transaction with risk signals |
| GET | `/api/security-events` | List security events (paginated, filterable) |
| GET | `/api/dashboard/summary` | KPI summary for dashboard |

---

## Synthetic Data (Phase 1)

The seed command creates:
- **12 autonomous agents** with varying statuses (active, suspended, pending_review, decommissioned)
- **Human/organization owners** with contact info
- **Spending permissions** as display-only fields (daily/monthly limits, allowed merchants)
- **91 payment requests** across statuses: approved (52), blocked (17), under_review (22), pending, failed
- **35 security events** of varying severity (info, warning, critical)
- **Mock risk scores** (0-100) and security events (velocity, geo-anomaly, amount-outlier, new-merchant, pattern deviation, limit breach, unauthorized merchant)

All data is clearly labeled as **synthetic demonstration data** in the UI.

---

## Testing

### Backend Tests
```powershell
cd C:\Users\5dars\Desktop\Paypal
.\.venv\Scripts\Activate.ps1
pytest backend/tests -v
```

### Frontend Tests
```powershell
cd C:\Users\5dars\Desktop\Paypal\frontend
npm test
```

---

## Development

### Backend Commands
```powershell
# Run with auto-reload
python -m backend.main

# Run tests with coverage
pytest backend/tests --cov=backend/app --cov-report=term-missing

# Type checking
mypy backend/app
```

### Frontend Commands
```powershell
cd frontend

# Development server
npm run dev

# Type checking
npm run typecheck

# Linting
npm run lint

# Build for production
npm run build

# Preview production build
npm run preview
```

---

## Known Limitations (Phase 1)

| Area | Limitation |
|------|------------|
| Authentication | No real agent identity verification - all agents pre-seeded |
| Authorization | Spending permissions are display-only, not enforced |
| Anomaly Detection | Risk scores are static mock values, not ML-based |
| Payments | No PayPal API integration - transaction status is simulated |
| Persistence | SQLite only; PostgreSQL migration planned for Phase 2 |
| Real-time | Polling-based updates (5s interval), not WebSocket |
| Security | CORS restricted to localhost only; no rate limiting |

---

## Phase 2 Roadmap

See [docs/roadmap.md](docs/roadmap.md) for detailed plans including:
- Real agent authentication (mTLS, JWT, certificate pinning)
- PayPal Orders v2 sandbox integration
- ML-based anomaly detection with explainable risk analysis
- WebSocket real-time updates
- PostgreSQL migration
- Audit logging and compliance reporting

---

## License

MIT License - Built for PayPal AI Hackathon 2026
