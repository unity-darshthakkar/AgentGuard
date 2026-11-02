import { useState } from 'react';
import { Play, ShieldCheck, ShieldX, BrainCircuit, LockKeyhole } from 'lucide-react';
import api from '../services/api';

type Scenario = { id: string; title: string; agent_id: string; merchant: string; amount_cents: number; verification_status: string; risk_score: number | null; risk_level?: string; decision: string; explanation: string; signals: { description?: string; signal?: string }[]; replay_rejected?: boolean };
type Simulation = { isolated: boolean; paypal_touched: boolean; scenarios: Scenario[] };

const money = (cents: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);

export function AttackSimulator() {
  const [result, setResult] = useState<Simulation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function run() {
    setLoading(true); setError('');
    try { setResult((await api.post<Simulation>('/attack-simulator/run')).data); }
    catch { setError('Simulation could not run. Confirm the admin API key is configured.'); }
    finally { setLoading(false); }
  }

  return <div className="space-y-6">
    <div className="card overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-primary-950 text-white">
      <div className="p-7 md:p-9 flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div className="max-w-2xl"><div className="badge bg-white/10 text-primary-200 mb-4">PHASE 5A · SAFE DEMO MODE</div><h2 className="text-3xl font-semibold tracking-tight">Attack Simulator</h2><p className="mt-3 text-slate-300 leading-7">Exercise AgentGuard’s real authorization pipeline against a trusted agent, a compromised behavioral profile, and a cryptographic impersonation attempt.</p></div>
        <button className="btn bg-white text-slate-900 hover:bg-primary-50 min-w-40" onClick={run} disabled={loading}><Play className="w-4 h-4" />{loading ? 'Running…' : 'Run simulation'}</button>
      </div>
      <div className="px-7 pb-6 flex flex-wrap gap-4 text-xs text-slate-300"><span className="inline-flex gap-2 items-center"><LockKeyhole className="w-4 h-4" />Server-side signing keys</span><span className="inline-flex gap-2 items-center"><ShieldCheck className="w-4 h-4" />Isolated database</span><span className="inline-flex gap-2 items-center"><ShieldX className="w-4 h-4" />No PayPal calls</span></div>
    </div>
    {error && <div className="card border-danger-200 bg-danger-50 p-4 text-danger-600">{error}</div>}
    {!result && !error && <div className="grid md:grid-cols-3 gap-4">{[['Legitimate agent', 'Valid signature · normal behavior', ShieldCheck], ['Compromised agent', 'Valid identity · anomalous behavior', BrainCircuit], ['Impersonation attack', 'Invalid or replayed authentication', ShieldX]].map(([title, text, Icon]) => <div className="card p-5" key={title as string}><Icon className="w-5 h-5 text-primary-600" /><h3 className="mt-4 font-semibold">{title as string}</h3><p className="mt-1 text-sm text-secondary-500">{text as string}</p></div>)}</div>}
    {result && <div className="space-y-4"><div className="flex items-center gap-2 text-sm text-secondary-500"><ShieldCheck className="w-4 h-4 text-success-600" />Results are isolated and synthetic · PayPal touched: {result.paypal_touched ? 'yes' : 'no'}</div>{result.scenarios.map(s => <article className="card p-5" key={s.id}><div className="flex flex-wrap justify-between gap-3"><div><p className="text-xs uppercase tracking-wider text-secondary-400">Scenario</p><h3 className="text-lg font-semibold">{s.title}</h3></div><span className={`badge ${s.decision === 'allow' ? 'badge-success' : s.decision === 'rejected' ? 'badge-danger' : 'badge-warning'}`}>{s.decision.toUpperCase()}</span></div><div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5 text-sm"><div><p className="text-secondary-400">Agent</p><p className="font-mono text-xs mt-1">{s.agent_id}</p></div><div><p className="text-secondary-400">Merchant / amount</p><p className="mt-1">{s.merchant} · {money(s.amount_cents)}</p></div><div><p className="text-secondary-400">Verification</p><p className="mt-1">{s.verification_status}{s.replay_rejected ? ' · replay rejected' : ''}</p></div><div><p className="text-secondary-400">Risk score</p><p className="mt-1 font-semibold">{s.risk_score ?? '—'}{s.risk_level ? ` · ${s.risk_level}` : ''}</p></div></div><p className="mt-5 rounded-lg bg-secondary-50 p-3 text-sm text-secondary-700">{s.explanation}</p>{s.signals.length > 0 && <div className="mt-3 flex flex-wrap gap-2">{s.signals.map((x, i) => <span className="badge badge-neutral" key={i}>{x.description || x.signal}</span>)}</div>}</article>)}</div>}
  </div>;
}
