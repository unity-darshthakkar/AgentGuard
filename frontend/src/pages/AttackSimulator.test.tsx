import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AttackSimulator } from './AttackSimulator';

vi.mock('../services/api', () => ({ default: { post: vi.fn().mockResolvedValue({ data: { isolated: true, paypal_touched: false, scenarios: [{ id: 'legitimate', title: 'Legitimate agent', merchant: 'merchant-grocery', amount_cents: 2500, authentication_outcome: 'verified', policy_outcome: 'allowed', risk_evaluated: false, risk_evaluation_reason: 'not_required_after_policy_authorization', risk_score: null, decision: 'allow', explanation: 'Allowed by policy.', reasons: ['Within policy limits'], signals: [], payment_status: 'authorized_for_checkout' }, { id: 'compromised', title: 'Compromised agent', merchant: 'merchant-new', amount_cents: 1000000, authentication_outcome: 'verified', policy_outcome: 'allowed', risk_evaluated: true, risk_score: 95, risk_level: 'critical', detection_method: 'ml_based', decision: 'block', explanation: 'Blocked before PayPal.', reasons: ['Behavioral risk exceeded threshold'], signals: [{ description: 'High transaction velocity' }], payment_status: 'denied_before_paypal' }, { id: 'impersonation', title: 'Impersonation / replay attack', merchant: 'merchant-unknown', amount_cents: 5000, authentication_outcome: 'replay_rejected', risk_evaluation_reason: 'authentication_rejected_first', policy_outcome: 'not_evaluated', risk_evaluated: false, risk_score: null, decision: 'rejected', explanation: 'Replay rejected.', reasons: ['Signature verification passed', 'Nonce replay rejected before authorization'], signals: [], payment_status: 'denied_before_authorization' }] } }) } }));

describe('AttackSimulator', () => {
  it('renders truthful allow, block, and replay risk paths', async () => {
    render(<AttackSimulator />);
    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));
    await waitFor(() => expect(screen.getByText('Compromised agent')).toBeInTheDocument());
    expect(screen.getByText('BLOCK')).toBeInTheDocument();
    expect(screen.getAllByText(/authorization permitted by policy/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/authentication rejected first/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Nonce replay rejected before authorization/)).toBeInTheDocument();
  });
});
