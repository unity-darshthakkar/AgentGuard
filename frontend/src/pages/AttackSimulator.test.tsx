import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AttackSimulator } from './AttackSimulator';
import api from '../services/api';
import { ATTACK_SIMULATOR_STORAGE_KEY } from './AttackSimulator';

vi.mock('../services/api', () => ({ default: { post: vi.fn().mockResolvedValue({ data: { isolated: true, paypal_touched: false, scenarios: [{ id: 'legitimate', title: 'Legitimate agent', merchant: 'merchant-grocery', amount_cents: 2500, authentication_outcome: 'verified', policy_outcome: 'allowed', risk_evaluated: false, risk_evaluation_reason: 'not_required_after_policy_authorization', risk_score: null, decision: 'allow', explanation: 'Allowed by policy.', reasons: ['Within policy limits'], signals: [], payment_status: 'authorized_for_checkout' }, { id: 'compromised', title: 'Compromised agent', merchant: 'merchant-new', amount_cents: 1000000, authentication_outcome: 'verified', policy_outcome: 'blocked', risk_evaluated: false, risk_evaluation_reason: 'policy_rejected_first', risk_score: null, decision: 'block', explanation: 'Blocked before risk analysis and PayPal.', reasons: ['Amount exceeds policy limit'], signals: [], payment_status: 'denied_before_paypal' }, { id: 'impersonation', title: 'Impersonation / replay attack', merchant: 'merchant-unknown', amount_cents: 5000, authentication_outcome: 'replay_rejected', risk_evaluation_reason: 'authentication_rejected_first', policy_outcome: 'not_evaluated', risk_evaluated: false, risk_score: null, decision: 'rejected', explanation: 'Replay rejected.', reasons: ['Signature verification passed', 'Nonce replay rejected before authorization'], signals: [], payment_status: 'denied_before_authorization' }] } }) } }));

describe('AttackSimulator', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.mocked(api.post).mockClear();
  });

  it('renders truthful allow, block, and replay risk paths', async () => {
    render(<AttackSimulator />);
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));
    await waitFor(() => expect(screen.getByText('Compromised agent')).toBeInTheDocument());
    expect(screen.getByText('BLOCK')).toBeInTheDocument();
    expect(screen.getAllByText(/authorization permitted by policy/).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getAllByText(/policy rejected first/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/authentication rejected first/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Nonce replay rejected before authorization/)).toBeInTheDocument();
  });

  it('restores the latest successful result after remounting', async () => {
    const first = render(<AttackSimulator />);
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));
    await waitFor(() => expect(screen.getByText('Compromised agent')).toBeInTheDocument());
    first.unmount();
    render(<AttackSimulator />);
    expect(screen.getByText('Compromised agent')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it('ignores outdated cached results', () => {
    window.sessionStorage.setItem(ATTACK_SIMULATOR_STORAGE_KEY, JSON.stringify({ version: 0, data: { isolated: true, paypal_touched: false, scenarios: [] } }));
    render(<AttackSimulator />);
    expect(screen.queryByText('BLOCK')).not.toBeInTheDocument();
  });

  it('reruns the backend simulator and replaces the cached result', async () => {
    render(<AttackSimulator />);
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));
    await waitFor(() => expect(screen.getByText('Compromised agent')).toBeInTheDocument());
    const cached = JSON.parse(window.sessionStorage.getItem(ATTACK_SIMULATOR_STORAGE_KEY) || '{}');
    cached.data.scenarios[0].title = 'Replacement result';
    vi.mocked(api.post).mockResolvedValueOnce({ data: cached.data });
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));
    await waitFor(() => expect(screen.getByText('Replacement result')).toBeInTheDocument());
    expect(api.post).toHaveBeenCalledTimes(2);
  });
});
