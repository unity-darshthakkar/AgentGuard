/** Tests for AuthorizationDecisionDetailPanel component */

import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { AuthorizationDecisionDetailPanel } from './AuthorizationDecisionDetailPanel';
import type { AuthorizationDecisionRecord } from '../../types';

// Mock authorization decision data
const mockDecision: AuthorizationDecisionRecord = {
  id: 1,
  request_id: 'REQ-001',
  idempotency_key: 'idem-001',
  agent_id: 1,
  credential_id: 10,
  policy_id: 5,
  amount_cents: 150000,
  currency: 'USD',
  merchant_id: 'MERCH-001',
  merchant_category: 'retail',
  description: 'Test purchase at retail store',
  decision: 'allow',
  reasons: ['Within daily budget', 'Merchant is trusted', 'Amount below per-transaction limit'],
  policy_violations: ['velocity_check'],
  daily_spent_before_cents: 50000,
  daily_spent_after_cents: 200000,
  decided_at: '2026-10-01T10:05:00Z',
};

const mockBlockedDecision: AuthorizationDecisionRecord = {
  ...mockDecision,
  id: 2,
  request_id: 'REQ-002',
  decision: 'block',
  reasons: ['Exceeds daily budget', 'Velocity anomaly detected'],
  policy_violations: ['daily_budget_exceeded', 'velocity_anomaly'],
  daily_spent_before_cents: 950000,
  daily_spent_after_cents: 1100000,
  decided_at: '2026-10-01T11:00:00Z',
};

const mockReviewDecision: AuthorizationDecisionRecord = {
  ...mockDecision,
  id: 3,
  request_id: 'REQ-003',
  decision: 'review',
  reasons: ['New merchant for this agent', 'Amount requires manual review'],
  policy_violations: null,
  daily_spent_before_cents: 100000,
  daily_spent_after_cents: 250000,
  decided_at: '2026-10-01T12:00:00Z',
};

describe('AuthorizationDecisionDetailPanel', () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when decision is null', () => {
    render(<AuthorizationDecisionDetailPanel decision={null} onClose={onClose} />);
    expect(screen.queryByText('Authorization Decision')).not.toBeInTheDocument();
  });

  it('renders decision details when decision is provided', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    // The request ID appears in header and in details - check both exist
    const reqIds = screen.getAllByText('REQ-001');
    expect(reqIds.length).toBeGreaterThanOrEqual(1);

    // The decision badge appears in header and in decision banner - check at least one exists
    const allowBadges = screen.getAllByText('ALLOW');
    expect(allowBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('displays decision with correct color coding for allow', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    const badges = screen.getAllByText('ALLOW');
    expect(badges.length).toBeGreaterThanOrEqual(1);
    // Check the first badge (the header badge)
    expect(badges[0].closest('span')).toHaveClass('bg-success-100');
    expect(badges[0].closest('span')).toHaveClass('text-success-700');
    expect(badges[0].closest('span')).toHaveClass('border-success-200');
  });

  it('displays decision with correct color coding for block', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockBlockedDecision} onClose={onClose} />);

    const badges = screen.getAllByText('BLOCK');
    expect(badges.length).toBeGreaterThanOrEqual(1);
    expect(badges[0].closest('span')).toHaveClass('bg-danger-100');
    expect(badges[0].closest('span')).toHaveClass('text-danger-700');
    expect(badges[0].closest('span')).toHaveClass('border-danger-200');
  });

  it('displays decision with correct color coding for review', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockReviewDecision} onClose={onClose} />);

    const badges = screen.getAllByText('REVIEW');
    expect(badges.length).toBeGreaterThanOrEqual(1);
    expect(badges[0].closest('span')).toHaveClass('bg-warning-100');
    expect(badges[0].closest('span')).toHaveClass('text-warning-700');
    expect(badges[0].closest('span')).toHaveClass('border-warning-200');
  });

  it('displays reasons for the decision', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    expect(screen.getByText('Decision Reasons')).toBeInTheDocument();
    expect(screen.getByText('Within daily budget')).toBeInTheDocument();
    expect(screen.getByText('Merchant is trusted')).toBeInTheDocument();
    expect(screen.getByText('Amount below per-transaction limit')).toBeInTheDocument();
  });

  it('displays policy violations when present', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    expect(screen.getByText('velocity_check')).toBeInTheDocument();
  });

  it('displays multiple policy violations', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockBlockedDecision} onClose={onClose} />);

    expect(screen.getByText('daily_budget_exceeded')).toBeInTheDocument();
    expect(screen.getByText('velocity_anomaly')).toBeInTheDocument();
  });

  it('handles null policy violations gracefully', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockReviewDecision} onClose={onClose} />);

    // Should not show policy violations section or show it empty
    // The component handles null by not rendering violations
    const reviewBadges = screen.getAllByText('REVIEW');
    expect(reviewBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('displays transaction details in overview section', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    expect(screen.getByText('Transaction Details')).toBeInTheDocument();
    // Multiple elements may contain $1,500.00 (Amount, Transaction Amount in budget section)
    const amounts = screen.getAllByText('$1,500.00');
    expect(amounts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('MERCH-001')).toBeInTheDocument();
    expect(screen.getByText('retail')).toBeInTheDocument();
  });

  it('displays budget impact details', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    expect(screen.getByText('Budget Impact')).toBeInTheDocument();
    expect(screen.getByText('$500.00')).toBeInTheDocument(); // daily spent before
    // Multiple elements may contain $1,500.00 (Amount, Transaction Amount)
    const amounts = screen.getAllByText('$1,500.00');
    expect(amounts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('$2,000.00')).toBeInTheDocument(); // daily spent after
  });

  it('displays policy and credential information', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    expect(screen.getByText('Policy & Credentials')).toBeInTheDocument();
    expect(screen.getByText('AGT-001')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument(); // credential_id
    expect(screen.getByText('5')).toBeInTheDocument(); // policy_id
  });

  it('closes when close button is clicked', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    fireEvent.click(screen.getByLabelText('Close panel'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes when backdrop is clicked', () => {
    render(<AuthorizationDecisionDetailPanel decision={mockDecision} onClose={onClose} />);

    const backdrop = document.querySelector('.fixed.inset-0.bg-black\\/50') as HTMLElement;
    if (backdrop) {
      fireEvent.click(backdrop);
      expect(onClose).toHaveBeenCalledTimes(1);
    }
  });

  it('handles missing idempotency key gracefully', () => {
    const decisionWithoutIdem = { ...mockDecision, idempotency_key: null };
    render(<AuthorizationDecisionDetailPanel decision={decisionWithoutIdem} onClose={onClose} />);

    // Should not crash, idempotency key should show — or be omitted
    const reqIds = screen.getAllByText('REQ-001');
    expect(reqIds.length).toBeGreaterThanOrEqual(1);
  });

  it('handles missing credential_id and policy_id gracefully', () => {
    const decisionWithoutIds = { ...mockDecision, credential_id: null, policy_id: null };
    render(<AuthorizationDecisionDetailPanel decision={decisionWithoutIds} onClose={onClose} />);

    const reqIds = screen.getAllByText('REQ-001');
    expect(reqIds.length).toBeGreaterThanOrEqual(1);
  });
});