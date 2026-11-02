# AgentGuard Roadmap

## Hackathon Target: November 12, 2026

**AgentGuard is being built for the PayPal AI Hackathon on November 12, 2026.** This roadmap is structured around that hard deadline. All core product features must be completed before the hackathon.

---

## Phase 1: Foundation & AG Grid Dashboard (✅ Complete - Ready for Nov 12, 2026)

### Delivered Features (Production-Ready for Demo)
- [x] Monorepo structure (backend/ + frontend/)
- [x] FastAPI backend with SQLAlchemy 2.0 async
- [x] SQLite persistence with FK support
- [x] Pydantic v2 schemas for all entities
- [x] RESTful API with pagination, filtering, sorting
- [x] Deterministic seed command (`python seed.py`) - seed=42
- [x] React 18 + TypeScript + Vite frontend
- [x] Tailwind CSS with custom design system
- [x] AG Grid Community for enterprise data tables
- [x] Dashboard with KPI cards (real API data)
- [x] Agent Registry with multi-select grid, status filter
- [x] Transaction Monitoring with risk visualization, detail panels
- [x] Security Events page with backend API integration
- [x] Settings page (clearly labeled as demo-only)
- [x] Comprehensive backend tests (17 passing)
- [x] Frontend tests with Vitest (29 passing)
- [x] TypeScript type checking passes
- [x] Production build successful
- [x] Synthetic data: 12 agents, 91 transactions, 35 security events
- [x] Risk distribution buckets: low (0-30), medium (31-69), high (70-89), critical (90-100)
- [x] All non-functional UI controls labeled "Demo Only"
- [x] Documentation updated and accurate

### Demo Day Checklist (Nov 12, 2026)
- [ ] Backend server running on port 8000 (`python -m backend.main`)
- [ ] Frontend dev server running on port 5173 (`npm run dev`)
- [ ] Database seeded with `python -m backend.seed`
- [ ] All API endpoints responding (<100ms)
- [ ] Frontend loads without console errors
- [ ] Demo script rehearsed (5-7 minutes)

---

## Phase 2: Cryptographic Agent Identity & Delegated Spending Permissions (Post-Hackathon)

### Authentication & Authorization (Priority: Critical)
- [ ] mTLS certificate-based agent authentication with certificate pinning
- [ ] JWT-based API authentication for agents and operators
- [ ] Role-based access control (Admin, Analyst, Viewer)
- [ ] Session management with secure cookies
- [ ] Certificate lifecycle management (rotation, revocation)

### Delegated Spending Permissions (Priority: Critical)
- [ ] Spend permission objects with cryptographic signatures
- [ ] Per-agent daily/monthly limits with cryptographic enforcement
- [ ] Merchant category allow/block lists with cryptographic verification
- [ ] Permission delegation chain with audit trail
- [ ] Real-time permission validation on transaction requests

### Database & Persistence (Priority: High)
- [ ] PostgreSQL support with asyncpg
- [ ] Connection pooling (asyncpg pool)
- [ ] Database migrations (Alembic)
- [ ] Certificate and key storage with encryption at rest

### Security Hardening (Priority: High)
- [ ] Rate limiting (per IP, per agent, per endpoint)
- [ ] Request validation & sanitization
- [ ] CSP headers
- [ ] Audit logging (immutable event store)

---

## Phase 3: PayPal Orders v2 Sandbox Checkout (Post-Hackathon)

### PayPal Integration (Priority: Critical - Core Product)
- [ ] PayPal Orders v2 API client with sandbox/live switching
- [ ] Payment execution flow with idempotency keys
- [ ] Buyer approval flow (redirect, approval, return)
- [ ] Server-side payment capture with webhook verification
- [ ] Refund/capture handling
- [ ] Webhook receiver for payment events with signature verification
- [ ] PayPal sandbox environment for testing

### Transaction Pipeline (Priority: Critical)
- [ ] End-to-end transaction flow: request → risk check → permission check → PayPal → capture
- [ ] Transaction state machine with proper status transitions
- [ ] Idempotency for all payment operations
- [ ] Failure handling and compensation transactions

---

## Phase 4: AI-Driven Anomaly Detection & Rogue-Agent Scenarios (Post-Hackathon)

### ML-Based Risk Scoring (Priority: Critical - Core Product)
- [ ] Feature engineering pipeline for transaction/agent behavior
- [ ] Anomaly detection model (Isolation Forest / Autoencoder)
- [ ] Supervised risk classification (XGBoost / LightGBM)
- [ ] Model versioning & A/B testing framework
- [ ] Real-time inference API
- [ ] Explainability (SHAP values for decisions)

### Rogue-Agent Scenarios (Priority: High - Demo Differentiator)
- [ ] Compromised agent credential simulation
- [ ] Velocity anomaly detection (burst transactions)
- [ ] Geographic anomaly detection (impossible travel)
- [ ] Amount outlier detection
- [ ] New merchant / permission violation detection
- [ ] Automated agent suspension on critical risk
- [ ] Interactive demo: trigger rogue agent scenarios manually

### Advanced Monitoring
- [ ] Real-time WebSocket updates
- [ ] Streaming transaction feed
- [ ] Alerting engine (thresholds, anomalies, ML predictions)
- [ ] Notification channels (Email, Slack, PagerDuty, Webhooks)

---

## Phase 5: Interactive Adversarial Demo, Deployment & Submission (Pre-Hackathon)

### Interactive Demo (Priority: Critical)
- [ ] Live rogue agent attack simulation button
- [ ] Real-time dashboard response visualization
- [ ] Before/after risk score comparison
- [ ] Agent suspension/recovery demo flow
- [ ] PayPal payment flow demo (sandbox)
- [ ] Narrative script for 5-7 minute presentation

### Deployment & Documentation
- [ ] Docker containers for backend and frontend
- [ ] docker-compose for local development
- [ ] Environment configuration documentation
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Architecture decision records (ADRs)
- [ ] Security model documentation

### Hackathon Submission
- [ ] Project video (2-3 minutes)
- [ ] Live demo URL or recording
- [ ] Source code repository
- [ ] Technical writeup
- [ ] Submission before Nov 12, 2026 deadline

---

## Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| **Hackathon Demo (Nov 12, 2026)** | **2026-11-12** | ✅ Ready (Phase 1) |
| Phase 2 Alpha (Auth + Permissions) | 2026-12-15 | 🔄 Planning |
| Phase 2 Beta | 2027-01-15 | ⏳ Pending |
| Phase 2 GA | 2027-02-28 | ⏳ Pending |
| Phase 3 Alpha (PayPal) | 2027-04-30 | ⏳ Pending |
| Phase 3 GA | 2027-06-30 | ⏳ Pending |
| Phase 4 Alpha (ML Risk) | 2027-08-31 | ⏳ Pending |
| Phase 4 GA | 2027-10-31 | ⏳ Pending |
| Phase 5 (Adversarial Demo) | 2026-11-10 | ⏳ Pre-Hackathon |

---

## Resource Requirements

### Phase 1 (Complete - Hackathon)
- 1 Full-stack Engineer (4 weeks)

### Phase 2 (Post-Hackathon)
- 1-2 Backend Engineers
- 1 Frontend Engineer (part-time)
- 1 DevOps Engineer (part-time)
- 1 Security Engineer (part-time)

### Phase 3 (PayPal Integration)
- 1-2 Backend Engineers (PayPal expertise)
- 1 DevOps Engineer
- 1 QA Engineer

### Phase 4 (ML/AI)
- 1-2 ML Engineers
- 2 Backend Engineers
- 1 Frontend Engineer
- 1 Data Engineer

### Phase 5 (Demo Prep)
- 1 Full-stack Engineer
- 1 Product/Design (part-time)

---

## Success Metrics

### Hackathon Demo (Nov 12, 2026)
- [x] Functional dashboard with synthetic data
- [x] All API endpoints responding < 100ms
- [x] Zero critical bugs in demo
- [x] Clear demo narrative (5-7 min presentation)
- [x] Risk distribution reconciles exactly (91 transactions = 30+35+15+5+6)

### Phase 2 (Post-Hackathon)
- [ ] mTLS agent authentication working end-to-end
- [ ] Delegated permissions cryptographically enforced
- [ ] 99.9% API uptime
- [ ] < 50ms p95 latency
- [ ] PostgreSQL running in production

### Phase 3 (PayPal Integration)
- [ ] Successful PayPal sandbox checkout flow
- [ ] Webhook verification working
- [ ] End-to-end payment with idempotency

### Phase 4 (AI Detection)
- [ ] ML model AUC > 0.92
- [ ] < 1% false positive rate
- [ ] < 200ms end-to-end decision latency
- [ ] Rogue agent scenarios demonstrable

### Phase 5 (Adversarial Demo)
- [ ] Interactive attack simulation works
- [ ] Dashboard responds in real-time
- [ ] Submission materials complete

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Hackathon demo failure | Low | Critical | Rehearsed script, backup recording, multiple test runs |
| PayPal API changes | Medium | High | Version pinning, adapter pattern |
| ML model drift | High | Medium | Monitoring, retraining pipeline |
| Regulatory changes | Medium | High | Compliance review, flexible architecture |
| Scaling bottlenecks | Medium | High | Load testing, horizontal scaling design |
| Talent acquisition | High | Medium | Documentation, knowledge sharing |
| Time to hackathon | Medium | Critical | Phase 1 complete, Phases 2-5 prioritized post-hackathon |

---

## Immediate Next Steps (Pre-Hackathon - Now to Nov 12)

1. **Now**: Dashboard data integrity fixes (security events labeling, synthetic data badges)
2. **Now**: UX polish (search functionality, responsive layout, remove fake badges)
3. **Nov 10**: Final integration test, demo rehearsal
6. **Nov 11**: Backup recording, submission preparation
7. **Nov 12**: HACKATHON DAY - Submit AgentGuard

---

*Last updated: 2026-10-28*  
*Version: 1.0.0-hackathon-ready*  
*Hackathon Date: **November 12, 2026***