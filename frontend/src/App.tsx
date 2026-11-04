/** Main App component with routing */

import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Overview } from './pages/Overview';
import { Agents } from './pages/Agents';
import { Transactions } from './pages/Transactions';
import { SecurityEvents } from './pages/SecurityEvents';
import { AuthorizationDecisions } from './pages/AuthorizationDecisions';
import { About } from './pages/About';
import { AttackSimulator } from './pages/AttackSimulator';

function App() {
  return (
    <Routes>
      <Route
        path="/attack-simulator"
        element={<Layout title="Attack Simulator" subtitle="Exercise AgentGuard safely with isolated demo scenarios"><AttackSimulator /></Layout>}
      />
      <Route
        path="/"
        element={
          <Layout title="Overview" subtitle="Security operations dashboard">
            <Overview />
          </Layout>
        }
      />
      <Route
        path="/agents"
        element={
          <Layout title="Agents" subtitle="Manage autonomous AI agents">
            <Agents />
          </Layout>
        }
      />
      <Route
        path="/transactions"
        element={
          <Layout title="Transactions" subtitle="Live transaction monitoring">
            <Transactions />
          </Layout>
        }
      />
      <Route
        path="/authorization-decisions"
        element={
          <Layout title="Authorization Decisions" subtitle="Review and analyze authorization outcomes">
            <AuthorizationDecisions />
          </Layout>
        }
      />
      <Route
        path="/security-events"
        element={
          <Layout title="Security Events" subtitle="Monitor and investigate anomalies">
            <SecurityEvents />
          </Layout>
        }
      />
      <Route
        path="/about"
        element={
          <Layout title="About" subtitle="Project information and roadmap">
            <About />
          </Layout>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

import { Navigate } from 'react-router-dom';

export default App;
