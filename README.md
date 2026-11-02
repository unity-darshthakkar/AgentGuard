# 🛡️ AgentGuard

### The Security Layer for Autonomous AI Payments

**Verify the agent. Enforce the rules. Detect the threat. Protect the payment.**

AgentGuard is an AI-powered security and authorization platform designed to protect payments initiated by autonomous AI agents. Built for the **PayPal AI Hackathon 2026**, it combines cryptographic agent authentication, granular spending permissions, behavioral anomaly detection, and real-time payment authorization to help prevent compromised, impersonated, or misconfigured AI agents from making unsafe purchases.

As AI agents become increasingly capable of shopping, subscribing, booking, and executing transactions on behalf of users, one question becomes critical:

**What happens when an AI agent has permission to spend money, but can no longer be trusted?**

AgentGuard addresses that challenge by introducing an independent security checkpoint between an AI agent's payment intent and PayPal's payment execution.

---

## The Problem

Traditional payment security systems are primarily designed around human users, merchants, accounts, and individual transactions.

Autonomous AI agents introduce a different set of risks:

- **Agent impersonation:** A malicious actor attempts to execute payments using another agent's identity.
- **Compromised agents:** A previously trusted agent begins initiating suspicious or unusually expensive transactions.
- **Excessive spending:** Agents exceed their intended budgets or make purchases outside their assigned permissions.
- **Replay attacks:** Previously signed requests are reused to attempt unauthorized or repeated operations.
- **Uncontrolled automation:** Automated systems make consequential payment decisions without sufficient oversight.
- **Duplicate payment execution:** Network retries or repeated requests result in unintended duplicate actions.

A valid API credential alone does not establish that an agent's current behavior is safe.

The challenge is not simply enabling AI agents to pay. It is ensuring that **the right agent can make the right payment, within the right limits, at the right time.**

## Our Solution

AgentGuard provides a multi-layer authorization system that evaluates an AI-initiated transaction before allowing it to proceed toward PayPal checkout.

Instead of relying on a single approval rule, the platform combines:

1. **Cryptographic identity verification** to establish which agent initiated the request.
2. **Permission-based access control** to enforce what that agent is allowed to do.
3. **Spending policy enforcement** to prevent transactions outside configured financial boundaries.
4. **Behavioral anomaly detection** to identify suspicious transaction patterns.
5. **Payment orchestration safeguards** to control checkout, capture, retries, and financial state reconciliation.
6. **Security monitoring and explainability** to help administrators understand decisions and investigate suspicious activity.

AgentGuard separates **authorization to initiate a payment** from **successful execution of a payment**. An `ALLOW` decision means that a request has passed the relevant AgentGuard controls; it does not mean that PayPal has completed a transaction.

## Key Features

### Cryptographically Verified Agent Identity

Every protected agent request can be authenticated using **Ed25519 digital signatures**.

AgentGuard verifies the request against the agent's registered public key and enforces credential and agent lifecycle restrictions.

Security controls include:

- Signed request verification
- Timestamp validity and expiration checks
- One-time nonce protection against replay attacks
- Credential revocation and expiration handling
- Suspended-agent restrictions
- Agent identity and permission boundaries

A replayed request cannot become trusted merely because its original signature was valid.

### Granular Spending Controls

AgentGuard applies configurable authorization policies to control how agents spend.

These controls include transaction limits, daily spending budgets, permissions, and safeguards around concurrent authorization requests.

Budget handling uses database-backed reservation logic to help prevent overspending during simultaneous requests. Authorization idempotency protections help ensure that repeated requests do not silently create independent approvals.

### AI-Powered Behavioral Risk Analysis

AgentGuard combines deterministic anomaly-detection rules with an **Isolation Forest** machine learning model.

The risk system is designed to identify unusual behavior such as spending outliers and transaction velocity anomalies.

The ML model is trained using **synthetically generated transaction data**, and its use is subject to available transaction history. Rule-based detection supports cold-start scenarios when sufficient behavioral history is unavailable.

Where risk evaluation takes place, the platform produces an interpretable risk assessment to support authorization decisions.

**Model transparency:** AgentGuard is a hackathon prototype. Its synthetic-data-trained model has not been established as production-validated fraud detection, and displayed risk scores should not be interpreted as calibrated probabilities of fraud.

### Real-Time Authorization Decisions

Protected requests flow through an authorization engine that applies identity, access, spending, and risk controls.

Possible outcomes include:

| Decision | Meaning |
|---|---|
| `ALLOW` | The request meets the applicable authorization requirements and may proceed to the next permitted payment step. |
| `REVIEW` | The request requires additional scrutiny and is not eligible for immediate checkout. |
| `BLOCK` | The request violates security or risk requirements and cannot proceed. |
| Authentication rejection | The request fails identity or anti-replay verification before downstream authorization. |

Security outcomes are accompanied by contextual explanations to improve visibility and troubleshooting.

### PayPal Sandbox Payment Integration

AgentGuard integrates with PayPal's Sandbox payment APIs for order creation and capture orchestration.

The implementation includes:

- PayPal Sandbox OAuth authentication
- Order creation and buyer approval handling
- Capture orchestration
- Idempotency protections for payment operations
- Amount and currency validation
- Local transaction and reservation state management
- Timeout and uncertain-state handling
- Payment reconciliation and budget settlement

Blocked, review-required, or unauthenticated requests must not initiate checkout.

The payment lifecycle distinguishes between the agent's authorization decision, PayPal order creation, buyer approval, and completed capture.

**Verification status:** Payment orchestration has been covered by automated tests using mocked PayPal responses. A complete externally verified Sandbox buyer approval and capture is a separate integration-validation milestone; no real-money payments are required for the demonstration.

### Interactive Attack Simulator

AgentGuard includes an isolated Attack Simulator designed to demonstrate how different agent behaviors pass through its security controls.

The simulator provides three scenarios:

| Scenario | Behavior | Expected outcome |
|---|---|---|
| Legitimate agent | An authorized $25 purchase within policy | `ALLOW` |
| Compromised agent | An anomalous $10,000 purchase attempt | `BLOCK` |
| Replay attack | A previously signed request is submitted with a reused nonce | Authentication rejected |

The simulator features a step-by-step security pipeline, risk visualizations where evaluation occurs, authorization explanations, payment-gate outcomes, and a guided walkthrough.

**The simulator uses isolated in-memory data and does not create or capture PayPal payments.**

### Security Operations Dashboard

The administrative interface provides visibility into autonomous payment activity through dedicated views for:

- **Overview:** Security activity, key metrics, and operational summaries
- **Agents:** Registered agents, credentials, and associated security information
- **Transactions:** Transaction history and payment status visibility
- **Authorization Decisions:** Approval, review, and blocking outcomes
- **Security Events:** Anomalies, alerts, and suspicious behaviors
- **Attack Simulator:** Interactive security scenarios and decision explanations
- **Settings:** Available configuration information and clearly identified unsupported controls

Supported data tables provide CSV export capabilities for the currently available filtered page data.

---

## How AgentGuard Works

```text
                    AUTONOMOUS AI AGENT
                             |
                             v
                   Payment Request
                             |
                             v
                +------------------------+
                | Agent Authentication   |
                | Ed25519 + Nonce Check  |
                +------------------------+
                             |
                             v
                +------------------------+
                | Permission Validation  |
                | Agent Access Controls  |
                +------------------------+
                             |
                             v
                +------------------------+
                | Spending Policies      |
                | Limits + Reservations  |
                +------------------------+
                             |
                             v
                +------------------------+
                | Behavioral Risk Engine |
                | Rules + Isolation      |
                | Forest (when eligible) |
                +------------------------+
                             |
                             v
                +------------------------+
                | Authorization Decision |
                +------------------------+
                    /       |        \
                   /        |         \
                ALLOW     REVIEW      BLOCK
                  |         |           |
                  v         v           v
             Payment     Hold for     Deny
               Gate      Review       Request
                  |
                  v
             PayPal Sandbox
                  |
                  v
             Buyer Approval
                  |
                  v
             Order Capture
                  |
                  v
           Reconcile Transaction
             & Settle Budget
```

Requests that fail authentication are rejected before later authorization stages. Risk evaluation is conditional: not every approved request necessarily undergoes ML inference.

This design separates **agent trust, spending authorization, and payment execution** into distinct responsibilities.

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite |
| Data Grid | AG Grid |
| Backend API | Python, FastAPI |
| Database | SQLite, SQLAlchemy |
| Migrations | Alembic |
| Machine Learning | Isolation Forest, scikit-learn |
| Cryptography | Ed25519 digital signatures |
| Payments | PayPal Sandbox REST APIs |
| Testing | pytest, Vitest |
| Development | Git, GitHub |

## Project Structure

```text
AgentGuard/
|
|-- backend/
|   |-- app/
|   |   |-- api/          # FastAPI routes
|   |   |-- core/         # Configuration and database
|   |   |-- models/       # Database models
|   |   |-- services/     # Security and payment services
|   |
|   |-- alembic/          # Database migrations
|   |-- tests/            # Backend regression tests
|   |-- train_model.py    # Synthetic ML training workflow
|
|-- frontend/
|   |-- src/
|   |   |-- components/   # Reusable UI components
|   |   |-- pages/        # Dashboard and simulator views
|   |   |-- services/     # API integration
|   |   |-- utils/        # Shared utilities
|
|-- docs/                 # Supporting project documentation
|-- .env.example          # Environment variable template
|-- README.md
```

## Getting Started

### Prerequisites

- Python and a supported virtual environment
- Node.js and npm
- Git
- PayPal Developer Sandbox credentials for external payment testing

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <repository-directory>
```

### 2. Configure the Environment

Copy the repository's `.env.example` into a new `.env` file and configure the required values.

Key configuration includes:

```dotenv
ADMIN_API_KEY=<generate-a-strong-local-development-key>
PAYPAL_CLIENT_ID=<your-sandbox-client-id>
PAYPAL_CLIENT_SECRET=<your-sandbox-client-secret>
PAYPAL_ENVIRONMENT=sandbox
```

Consult `.env.example` for the complete configuration supported by the repository.

Never commit `.env`, private signing keys, or PayPal credentials.

### 3. Start the Backend

From the project root:

```bash
python -m venv .venv
```

Activate the virtual environment using the appropriate command for your operating system.

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies using the dependency manifest supplied in `backend/`.

Apply the reviewed Alembic database migrations:

```bash
cd backend
alembic upgrade head
```

Start FastAPI:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

The API documentation is available at:

`http://127.0.0.1:8001/docs`

### 4. Start the Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL displayed by Vite.

The frontend uses relative `/api` requests in local development. The development proxy forwards them to the FastAPI backend.

**Security note:** The repository's local development proxy can attach an admin credential server-side for supported requests. This is a private local-development convenience, not an internet-facing authentication solution. A publicly accessible deployment must use independently secured authentication and authorization.

### 5. Explore the Attack Simulator

Open the **Attack Simulator** from the navigation sidebar and select **Run Simulation**.

Observe how the security pipeline handles a legitimate payment request, a compromised-agent attempt, and a replay attack.

The simulator is intended for demonstration and does not execute PayPal transactions.

## Testing

AgentGuard includes automated tests for agent authentication, policy enforcement, authorization behavior, spending limits, idempotency, anomaly detection, payment orchestration, and the Attack Simulator.

Backend tests:

```bash
cd backend
python -m pytest tests -q
```

Frontend tests:

```bash
cd frontend
npm test -- --run
```

Production frontend build:

```bash
cd frontend
npm run build
```

The application has undergone automated regression testing, including mocked PayPal order and capture workflows. Passing tests do not substitute for external Sandbox buyer-approval and capture verification or a production security assessment.

## Security Design

AgentGuard is designed around a central principle:

**An AI agent's ability to make a request should not automatically grant it permission to spend money.**

The system applies multiple controls to reduce dependence on any single layer of trust.

Its security approach emphasizes:

- Cryptographic request authentication
- Replay prevention
- Least-privilege agent access
- Financial limits and budget reservations
- Behavioral anomaly detection
- Fail-closed handling of uncertain payment states
- Payment idempotency and reconciliation
- Separation of authorization from capture
- Administrative monitoring and auditability

The public demonstration should use synthetic or non-sensitive data, and payment-related administrative capabilities should remain protected.

AgentGuard is a prototype intended for development, research, and controlled demonstration. It is not certified as a production payment-security or fraud-prevention system.

## Challenges and Lessons Learned

Building AgentGuard required addressing several challenges that arise when autonomous software is allowed to interact with financial systems.

**Trust is more than authentication.** A validly signed transaction can still be inappropriate. Identity verification must work alongside spending policies and behavioral analysis.

**Financial state requires careful coordination.** Authorization, spending reservations, PayPal orders, buyer approval, capture, and reconciliation represent different states. Handling retries and failures safely is essential.

**AI risk analysis needs honest explanations.** A rule-based decision should not be described as an ML prediction, and requests rejected during authentication should not receive fabricated risk scores.

**Security demonstrations must remain safe.** The Attack Simulator was designed around isolated data and server-side signing material so attacks can be demonstrated without creating payments.

**Operational reliability matters.** Configuration management, database migrations, regression testing, and frontend-to-backend connectivity are fundamental parts of making a security product credible.

## Future Roadmap

AgentGuard establishes a foundation for protecting payments executed by increasingly autonomous software agents.

Potential future directions include:

- Production-grade, multi-user administrative authentication
- Broader agent identity and credential-management integrations
- Human-in-the-loop approval workflows
- Additional behavioral signals and agent risk models
- Risk evaluation using appropriately governed real-world data
- Merchant- and organization-level policy management
- Expanded payment-provider support
- More advanced transaction investigation and audit tooling
- Deployment hardening, observability, and scalability improvements

The long-term vision is to make trustworthy agent authorization an integral part of the emerging agentic commerce ecosystem.

## Live Demo

**Deployment:** Render — live application URL to be added.

The hosted demonstration is intended to showcase AgentGuard's dashboard, authorization workflow, and isolated Attack Simulator. Access to payment execution and sensitive administrative operations must remain appropriately restricted.

## Built for the PayPal AI Hackathon 2026

AgentGuard explores an emerging challenge in digital commerce: **how to safely authorize financial actions when the actor initiating a payment is an autonomous AI agent rather than a human.**

By combining cryptographic identity, policy enforcement, behavioral intelligence, and PayPal payment orchestration, AgentGuard demonstrates an approach to building safer, more accountable agentic payment experiences.

---

**AgentGuard — Because autonomous payments need autonomous protection.**