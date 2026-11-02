/** Tests for AuthorizationDecisions page */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AuthorizationDecisions } from './AuthorizationDecisions';
import type { AuthorizationDecisionRecord } from '../types';

// Mock the useAuthorizationDecisions hook
vi.mock('../hooks/useApi', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual as any,
    useAuthorizationDecisions: vi.fn(),
  };
});

import { useAuthorizationDecisions } from '../hooks/useApi';

// Mock decision data
const mockDecisions: AuthorizationDecisionRecord[] = [
  {
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
    reasons: ['Within daily budget', 'Merchant is trusted'],
    policy_violations: ['velocity_check'],
    daily_spent_before_cents: 50000,
    daily_spent_after_cents: 200000,
    decided_at: '2026-10-01T10:05:00Z',
  },
  {
    id: 2,
    request_id: 'REQ-002',
    idempotency_key: 'idem-002',
    agent_id: 2,
    credential_id: 11,
    policy_id: 6,
    amount_cents: 250000,
    currency: 'USD',
    merchant_id: 'MERCH-002',
    merchant_category: 'software',
    description: 'Software subscription',
    decision: 'block',
    reasons: ['Exceeds daily budget'],
    policy_violations: ['daily_budget_exceeded'],
    daily_spent_before_cents: 950000,
    daily_spent_after_cents: 1200000,
    decided_at: '2026-10-01T11:00:00Z',
  },
  {
    id: 3,
    request_id: 'REQ-003',
    idempotency_key: 'idem-003',
    agent_id: 1,
    credential_id: 10,
    policy_id: 5,
    amount_cents: 75000,
    currency: 'USD',
    merchant_id: 'MERCH-003',
    merchant_category: 'food',
    description: 'Food delivery',
    decision: 'review',
    reasons: ['New merchant', 'Amount requires review'],
    policy_violations: null,
    daily_spent_before_cents: 200000,
    daily_spent_after_cents: 275000,
    decided_at: '2026-10-01T12:00:00Z',
  },
];

const mockPagination = {
  page: 1,
  page_size: 20,
  total: 3,
  total_pages: 1,
};

const createMockHookReturn = (overrides: Partial<{
  items: AuthorizationDecisionRecord[];
  loading: boolean;
  error: string | null;
  total: number;
  totalPages: number;
  hasData: boolean;
}> = {}) => {
  const hasData = overrides.hasData ?? !overrides.loading;
  return {
    data: hasData ? {
      items: overrides.items ?? mockDecisions,
      total: overrides.total ?? mockPagination.total,
      page: mockPagination.page,
      page_size: mockPagination.page_size,
      total_pages: overrides.totalPages ?? mockPagination.total_pages,
    } : undefined,
    loading: overrides.loading ?? false,
    error: overrides.error ?? null,
    refetch: vi.fn(),
    pagination: { page: 1, page_size: 20 },
    setPagination: vi.fn(),
    totalPages: overrides.totalPages ?? 1,
  };
};

describe('AuthorizationDecisions', () => {
  const mockUseAuthorizationDecisions = useAuthorizationDecisions as ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthorizationDecisions.mockReturnValue(createMockHookReturn());
  });

  it('renders authorization decisions from API data', async () => {
    render(<AuthorizationDecisions />);

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading authorization decisions...')).not.toBeInTheDocument();
    });

    // Check that decisions are rendered (AG Grid renders them in the DOM)
    expect(screen.getByText('REQ-001')).toBeInTheDocument();
    expect(screen.getByText('REQ-002')).toBeInTheDocument();
    expect(screen.getByText('REQ-003')).toBeInTheDocument();

    // Check decision badges (may appear multiple times)
    const allowBadges = screen.getAllByText('ALLOW');
    expect(allowBadges.length).toBeGreaterThanOrEqual(1);

    const blockBadges = screen.getAllByText('BLOCK');
    expect(blockBadges.length).toBeGreaterThanOrEqual(1);

    const reviewBadges = screen.getAllByText('REVIEW');
    expect(reviewBadges.length).toBeGreaterThanOrEqual(1);

    // Check amounts
    expect(screen.getByText('$1,500.00')).toBeInTheDocument();
    expect(screen.getByText('$2,500.00')).toBeInTheDocument();
    expect(screen.getByText('$750.00')).toBeInTheDocument();

    // Check merchants
    expect(screen.getByText('MERCH-001')).toBeInTheDocument();
    expect(screen.getByText('MERCH-002')).toBeInTheDocument();
    expect(screen.getByText('MERCH-003')).toBeInTheDocument();
  });

  it('shows loading state while fetching', () => {
    // When loading=true and no data, LoadingState component is shown
    mockUseAuthorizationDecisions.mockReturnValue(createMockHookReturn({
      loading: true,
      hasData: false,
      items: [],
      total: 0,
      totalPages: 0,
    }));

    render(<AuthorizationDecisions />);

    expect(screen.getByText('Loading authorization decisions...')).toBeInTheDocument();
  });

  it('shows error state when fetch fails', () => {
    mockUseAuthorizationDecisions.mockReturnValue(createMockHookReturn({
      loading: false,
      error: 'Failed to fetch authorization decisions',
      hasData: false,
      items: [],
      total: 0,
      totalPages: 0,
    }));

    render(<AuthorizationDecisions />);

    // Use a flexible matcher since text might be broken up
    expect(screen.getByText(/unable to load data/i)).toBeInTheDocument();
    expect(screen.getByText('Failed to fetch authorization decisions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('shows empty state when no decisions exist', async () => {
    mockUseAuthorizationDecisions.mockReturnValue(createMockHookReturn({
      items: [],
      total: 0,
      totalPages: 0,
    }));

    render(<AuthorizationDecisions />);

    await waitFor(() => {
      expect(screen.queryByText('Loading authorization decisions...')).not.toBeInTheDocument();
    });

    expect(screen.getByText('No authorization decisions found')).toBeInTheDocument();
    expect(screen.getByText('No authorization decisions recorded yet')).toBeInTheDocument();
  });

  it('filters decisions by search query', async () => {
    render(<AuthorizationDecisions />);

    await waitFor(() => {
      expect(screen.queryByText('Loading authorization decisions...')).not.toBeInTheDocument();
    });

    // Search for REQ-001
    const searchInput = screen.getByPlaceholderText('Search decisions (request ID, agent, merchant, category)...');
    fireEvent.change(searchInput, { target: { value: 'REQ-001' } });

    await waitFor(() => {
      expect(screen.getByText('REQ-001')).toBeInTheDocument();
    });

    // REQ-002 and REQ-003 should not be visible (filtered out)
    expect(screen.queryByText('REQ-002')).not.toBeInTheDocument();
    expect(screen.queryByText('REQ-003')).not.toBeInTheDocument();
  });

  it('shows refresh button', async () => {
    render(<AuthorizationDecisions />);

    await waitFor(() => {
      expect(screen.queryByText('Loading authorization decisions...')).not.toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
  });

  it('displays pagination info', async () => {
    // Need totalPages > 1 to show pagination
    mockUseAuthorizationDecisions.mockReturnValue(createMockHookReturn({
      totalPages: 2,
      total: 25,
    }));

    render(<AuthorizationDecisions />);

    await waitFor(() => {
      expect(screen.queryByText('Loading authorization decisions...')).not.toBeInTheDocument();
    });

    // Text may be broken up across elements, use flexible matcher
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();
    expect(screen.getByText(/25 total/)).toBeInTheDocument();
  });
});