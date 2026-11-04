/** About page */

import { Github, Shield, Zap, Users, Code2, Database, Globe, Info } from 'lucide-react';

const features = [
  {
    icon: Shield,
    title: 'Zero-Trust Architecture',
    description: 'Every agent transaction is verified through identity validation, permission checks, and risk analysis before execution.',
  },
  {
    icon: Zap,
    title: 'Real-time Monitoring',
    description: 'Live transaction streaming with sub-second latency, configurable alerts, and automated threat response.',
  },
  {
    icon: Users,
    title: 'Agent Registry',
    description: 'Centralized management of autonomous agents with delegated spending permissions and audit trails.',
  },
  {
    icon: Code2,
    title: 'Explainable Risk Analysis',
    description: 'ML-powered anomaly detection with human-readable risk signals and decision explanations.',
  },
  {
    icon: Database,
    title: 'Audit & Compliance',
    description: 'Immutable audit logs, compliance reporting, and data retention policies for regulatory requirements.',
  },
  {
    icon: Globe,
    title: 'PayPal Integration',
    description: 'Native PayPal Orders v2 support for secure payment execution with sandbox and production environments.',
  },
];

const techStack = [
  { name: 'React 18', category: 'Frontend', description: 'Modern React with hooks and concurrent features' },
  { name: 'TypeScript', category: 'Frontend', description: 'Type-safe development experience' },
  { name: 'Vite', category: 'Frontend', description: 'Fast build tool and dev server' },
  { name: 'Tailwind CSS', category: 'Frontend', description: 'Utility-first CSS framework' },
  { name: 'AG Grid', category: 'Frontend', description: 'Enterprise-grade data grid component' },
  { name: 'FastAPI', category: 'Backend', description: 'High-performance Python web framework' },
  { name: 'SQLAlchemy 2.0', category: 'Backend', description: 'Modern Python ORM with async support' },
  { name: 'Pydantic v2', category: 'Backend', description: 'Data validation and serialization' },
  { name: 'SQLite / PostgreSQL', category: 'Database', description: 'Relational database for persistence' },
  { name: 'Pytest / Vitest', category: 'Testing', description: 'Unit and integration testing frameworks' },
];

const roadmap = [
  {
    phase: 'Foundation',
    title: 'Foundation & Demo',
    status: 'complete',
    items: [
      'Monorepo structure with frontend/backend separation',
      'FastAPI backend with REST endpoints',
      'SQLAlchemy models for Agent, Transaction, SecurityEvent',
      'Deterministic synthetic data seeder (12 agents, 91 transactions, 35 events)',
      'React dashboard with AG Grid tables',
      'KPI dashboard with real-time polling',
      'Transaction detail panel with risk signals',
      'CORS, Pydantic validation, comprehensive tests',
    ],
  },
  {
    phase: 'Authentication & Payments',
    title: 'Implemented identity, policy, and payment controls',
    status: 'complete',
    items: [
      'Ed25519-signed agent requests with timestamp validation and single-use nonce replay protection',
      'Delegated spending-policy enforcement for currencies, merchants, transaction limits, and daily budgets',
      'PayPal Orders v2 Sandbox order creation and capture orchestration',
      'One genuine $5.00 USD PayPal Sandbox end-to-end test passed: signed authorization, buyer approval, capture, and budget settlement',
      'Admin API-key authentication for privileged operational routes and a rate-limited public Attack Simulator',
      'PostgreSQL-compatible SQLAlchemy/Alembic migrations are available; WebSocket replacement for HTTP polling and general API rate limiting remain future work',
    ],
  },
  {
    phase: 'AI Anomaly Detection',
    title: 'AI Anomaly Detection',
    status: 'planned',
    items: [
      'scikit-learn based isolation forest for anomaly detection',
      'Explainable risk scoring with SHAP values',
      'Behavioral baselines per agent',
      'Automated model retraining pipeline',
      'False positive reduction feedback loop',
    ],
  },
  {
    phase: 'Production Hardening',
    title: 'Production Hardening',
    status: 'planned',
    items: [
      'Kubernetes deployment manifests',
      'Prometheus/Grafana observability stack',
      'SOC 2 compliance documentation',
      'Multi-region disaster recovery',
      'Advanced RBAC and audit logging',
    ],
  },
];

export function About() {
  return (
    <>
      {/* Hero */}
      <div className="card p-8 md:p-12 mb-8 text-center">
        <div className="w-20 h-20 rounded-2xl bg-primary-100 flex items-center justify-center mx-auto mb-6">
          <svg className="w-12 h-12 text-primary-600" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="32" height="32" rx="8" fill="currentColor"/>
            <path d="M8 12h16M8 16h12M8 20h8" stroke="white" stroke-width="2" stroke-linecap="round"/>
            <path d="M20 16v8" stroke="white" stroke-width="2" stroke-linecap="round"/>
            <circle cx="24" cy="24" r="4" fill="#ef4444"/>
          </svg>
        </div>
        <h1 className="text-3xl md:text-4xl font-bold text-secondary-900 mb-4">AgentGuard</h1>
        <p className="text-lg text-secondary-600 max-w-2xl mx-auto mb-6">
          Zero-trust security gateway for autonomous AI agents making payments through PayPal.
          Verifies agent identities, checks delegated spending permissions, detects suspicious behavior,
          and prevents unauthorized payment execution.
        </p>
        <div className="flex items-center justify-center gap-4">
          <a href="https://github.com/unity-darshthakkar/AgentGuard" target="_blank" rel="noopener noreferrer" className="btn-primary">
            <Github className="w-4 h-4" />
            View on GitHub
          </a>
          <a href="#roadmap" className="btn-secondary">View Roadmap</a>
        </div>
      </div>

      {/* Product status notice */}
      <div className="mb-6 p-3 bg-primary-50 border border-primary-200 rounded-lg">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center flex-shrink-0">
            <Info className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <p className="font-medium text-primary-800">PayPal AI Hackathon 2026 demonstration</p>
            <p className="text-xs text-primary-600 mt-1">
              The security gateway implements signed agent identity verification, spending-policy authorization, and explainable anomaly analysis. A real $5.00 USD PayPal Sandbox payment completed end to end in the local integration test, including signed authorization, buyer approval, capture, and budget settlement. This public Render dashboard uses synthetic data; its Attack Simulator runs in an isolated in-memory environment and never performs PayPal transactions. The verified Sandbox flow is local test evidence only and is not exposed through this public demo; PayPal Live and production payment processing are not claimed.
            </p>
          </div>
        </div>
      </div>

      {/* Features */}
      <section className="mb-12">
        <h2 className="text-2xl font-bold text-secondary-900 mb-6">Key Features</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, index) => (
            <div key={index} className="card p-6 hover:shadow-md transition-shadow">
              <div className="w-12 h-12 rounded-xl bg-primary-100 flex items-center justify-center mb-4">
                <feature.icon className="w-6 h-6 text-primary-600" />
              </div>
              <h3 className="text-lg font-semibold text-secondary-900 mb-2">{feature.title}</h3>
              <p className="text-secondary-600">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Tech Stack */}
      <section className="mb-12">
        <h2 className="text-2xl font-bold text-secondary-900 mb-6">Technology Stack</h2>
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-secondary-50 border-b border-secondary-200">
                <th className="px-6 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Technology</th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Category</th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {techStack.map((tech, index) => (
                <tr key={index} className="hover:bg-secondary-50">
                  <td className="px-6 py-4">
                    <code className="font-mono text-sm text-secondary-900">{tech.name}</code>
                  </td>
                  <td className="px-6 py-4">
                    <span className="badge badge-info">{tech.category}</span>
                  </td>
                  <td className="px-6 py-4 text-sm text-secondary-600">{tech.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Roadmap */}
      <section id="roadmap" className="mb-12">
        <h2 className="text-2xl font-bold text-secondary-900 mb-6">Roadmap</h2>
        <div className="space-y-6">
          {roadmap.map((phase, index) => (
            <div key={index} className="card overflow-hidden">
              <div className={`px-6 py-4 border-b border-secondary-200 flex items-center justify-between ${
                phase.status === 'complete' ? 'bg-success-50' : 'bg-warning-50'
              }`}>
                <div className="flex items-center gap-3">
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                    phase.status === 'complete' ? 'bg-success-100 text-success-600' : 'bg-warning-100 text-warning-600'
                  }`}>
                    {phase.status === 'complete' ? '✓ Complete' : '📋 Planned'}
                  </span>
                  <div>
                    <h3 className="font-semibold text-secondary-900">{phase.phase}</h3>
                    <p className="text-sm text-secondary-500">{phase.title}</p>
                  </div>
                </div>
              </div>
              <div className="p-6">
                <ul className="space-y-2">
                  {phase.items.map((item, i) => (
                    <li key={i} className="flex items-start gap-3 text-secondary-600">
                      <span className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                        phase.status === 'complete' ? 'text-success-500' : 'text-warning-500'
                      }`}>
                        {phase.status === 'complete' ? '✓' : '○'}
                      </span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Project Info */}
      <section className="mb-8">
        <h2 className="text-2xl font-bold text-secondary-900 mb-6">Project Information</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="card p-6">
            <h3 className="font-semibold text-secondary-900 mb-4 flex items-center gap-2">
              <Code2 className="w-5 h-5 text-primary-600" />
              Repository
            </h3>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between"><dt className="text-secondary-500">Structure</dt><dd className="font-mono text-secondary-900">Monorepo (frontend/backend/docs)</dd></div>
              <div className="flex justify-between"><dt className="text-secondary-500">License</dt><dd className="text-secondary-900">MIT</dd></div>
              <div className="flex justify-between"><dt className="text-secondary-500">Version</dt><dd className="font-mono text-secondary-900">1.0.0</dd></div>
            </dl>
          </div>
          <div className="card p-6">
            <h3 className="font-semibold text-secondary-900 mb-4 flex items-center gap-2">
              <Database className="w-5 h-5 text-primary-600" />
              Data Models
            </h3>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between"><dt className="text-secondary-500">Agent</dt><dd className="text-secondary-900">12 fields + relationships</dd></div>
              <div className="flex justify-between"><dt className="text-secondary-500">Transaction</dt><dd className="text-secondary-900">16 fields + risk scoring</dd></div>
              <div className="flex justify-between"><dt className="text-secondary-500">SecurityEvent</dt><dd className="text-secondary-900">6 event types, 3 severities</dd></div>
            </dl>
          </div>
          <div className="card p-6">
            <h3 className="font-semibold text-secondary-900 mb-4 flex items-center gap-2">
              <Shield className="w-5 h-5 text-primary-600" />
              Security
            </h3>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between"><dt className="text-secondary-500">CORS</dt><dd className="text-secondary-900">Restricted to the AgentGuard Render frontend origin</dd></div>
              <div className="flex justify-between"><dt className="text-secondary-500">Secrets</dt><dd className="text-secondary-900">Excluded via .gitignore</dd></div>
              <div className="flex justify-between"><dt className="text-secondary-500">Validation</dt><dd className="text-secondary-900">Pydantic schemas on all endpoints</dd></div>
            </dl>
          </div>
        </div>
      </section>

      {/* Footer */}
      <div className="text-center py-8 border-t border-secondary-200">
        <p className="text-secondary-500">
          Built for <strong>PayPal AI Hackathon 2026</strong> •
            <a href="https://github.com/unity-darshthakkar/AgentGuard" target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline">
            Open Source
          </a> •
          MIT Licensed
        </p>
      </div>
    </>
  );
}
