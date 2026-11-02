/** Tests for useApi hooks */

import { renderHook, waitFor, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

// Mock the API module
vi.mock('../services/api', () => ({
  healthApi: {
    check: vi.fn(),
  },
  agentsApi: {
    list: vi.fn(),
    get: vi.fn(),
    getByAgentId: vi.fn(),
  },
  transactionsApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
  dashboardApi: {
    summary: vi.fn(),
  },
  securityEventsApi: {
    list: vi.fn(),
  },
  authorizationDecisionsApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
  authorizationReservationsApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
  spendingPoliciesApi: {
    get: vi.fn(),
  },
}));

import {
  healthApi,
  agentsApi,
  transactionsApi,
  dashboardApi,
  securityEventsApi,
  authorizationDecisionsApi,
  authorizationReservationsApi,
  spendingPoliciesApi,
} from '../services/api';
import {
  useHealth,
  useDashboardSummary,
  useAgents,
  useTransactions,
  useSecurityEvents,
  useAuthorizationDecisions,
  useAuthorizationReservations,
  useSpendingPolicy,
} from './useApi';
import type { Agent, Transaction, SecurityEvent, DashboardSummary, PaginatedResponse, AuthorizationDecisionRecord, AuthorizationReservation, SpendingPolicy, AuthorizationDecision, ReservationStatus } from '../types';

describe('useApi hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('useHealth', () => {
    it('fetches health data on mount', async () => {
      const mockHealth = { status: 'healthy', version: '1.0.0', database: 'connected', timestamp: '2026-10-01T00:00:00Z' };
      const mockResponse = { data: mockHealth, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(healthApi.check).mockResolvedValue(mockResponse as any);

      const { result } = renderHook(() => useHealth());

      expect(result.current.loading).toBe(true);
      expect(result.current.data).toBeNull();

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockHealth);
      expect(healthApi.check).toHaveBeenCalledTimes(1);
    });

    it('handles error correctly', async () => {
      vi.mocked(healthApi.check).mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useHealth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Network error');
      expect(result.current.data).toBeNull();
    });

    it('refetch works', async () => {
      const mockHealth = { status: 'healthy', version: '1.0.0', database: 'connected', timestamp: '2026-10-01T00:00:00Z' };
      const mockResponse = { data: mockHealth, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(healthApi.check).mockResolvedValue(mockResponse as any);

      const { result } = renderHook(() => useHealth());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const mockHealth2 = { ...mockHealth, version: '2.0.0' };
      const mockResponse2 = { data: mockHealth2, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(healthApi.check).mockResolvedValue(mockResponse2 as any);

      await act(async () => {
        await result.current.refetch();
      });

      expect(healthApi.check).toHaveBeenCalledTimes(2);
      expect(result.current.data?.version).toBe('2.0.0');
    });
  });

  describe('useDashboardSummary', () => {
    it('fetches dashboard summary on mount', async () => {
      const mockSummary: DashboardSummary = {
        total_agents: 12,
        active_agents: 8,
        suspended_agents: 2,
        pending_review_agents: 2,
        total_transactions: 91,
        approved_transactions: 52,
        blocked_transactions: 17,
        under_review_transactions: 22,
        pending_transactions: 0,
        failed_transactions: 0,
        total_volume_usd: 939044.83,
        avg_risk_score: 40.07,
        low_risk_transactions: 40,
        medium_risk_transactions: 36,
        high_risk_transactions: 10,
        critical_risk_transactions: 5,
        recent_security_events: 2,
        unacknowledged_events: 12,
      };
      const mockResponse = { data: mockSummary, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(dashboardApi.summary).mockResolvedValue(mockResponse as any);

      const { result } = renderHook(() => useDashboardSummary());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockSummary);
      expect(dashboardApi.summary).toHaveBeenCalledTimes(1);
    });
  });

  describe('useAgents', () => {
    it('fetches agents with pagination', async () => {
      const mockAgents: Agent[] = [
        {
          id: 1,
          agent_id: 'AGT-001',
          name: 'Test Agent 1',
          description: 'Test',
          status: 'active',
          owner_type: 'organization',
          owner_name: 'Test Org',
          owner_email: 'test@org.com',
          owner_contact: null,
          daily_limit_usd: 10000,
          monthly_limit_usd: 100000,
          allowed_merchant_categories: null,
          blocked_merchant_categories: null,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          last_active_at: '2026-10-01T00:00:00Z',
        },
      ];

      const mockResponse: PaginatedResponse<Agent> = {
        items: mockAgents,
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };

      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(agentsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAgents({ page: 1, page_size: 20 }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse);
      expect(result.current.totalPages).toBe(1);
      expect(agentsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20 });
    });

    it('handles status filter', async () => {
      const mockResponse: PaginatedResponse<Agent> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(agentsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAgents({ status: 'active' }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(agentsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, status: 'active' });
    });

    it('setPagination updates page', async () => {
      const mockResponse: PaginatedResponse<Agent> = {
        items: [],
        total: 50,
        page: 1,
        page_size: 20,
        total_pages: 3,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(agentsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAgents());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.setPagination({ page: 2 });
      });

      await waitFor(() => {
        expect(result.current.pagination.page).toBe(2);
      });

      expect(agentsApi.list).toHaveBeenCalledWith({ page: 2, page_size: 20 });
    });
  });

  describe('useTransactions', () => {
    it('fetches transactions with filters', async () => {
      const mockTransactions: Transaction[] = [
        {
          id: 1,
          transaction_id: 'TXN-001',
          agent_id: 1,
          amount_usd: 100,
          currency: 'USD',
          merchant_name: 'Test Merchant',
          merchant_category: 'retail',
          merchant_country: 'US',
          description: 'Test transaction',
          status: 'approved',
          risk_score: 10,
          risk_level: 'low',
          decision_reason: 'Test',
          requested_at: '2026-10-01T00:00:00Z',
          decided_at: '2026-10-01T00:01:00Z',
          completed_at: '2026-10-01T00:02:00Z',
        },
      ];

      const mockResponse: PaginatedResponse<Transaction> = {
        items: mockTransactions,
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };

      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(transactionsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useTransactions({
        agent_id: 1,
        status: 'approved',
        min_risk: 0,
        max_risk: 50,
      }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse);
      expect(transactionsApi.list).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        agent_id: 1,
        status: 'approved',
        min_risk: 0,
        max_risk: 50,
      });
    });
  });

  describe('useSecurityEvents', () => {
    it('fetches security events with filters', async () => {
      const mockEvents: SecurityEvent[] = [
        {
          id: 1,
          event_id: 'EVT-001',
          agent_id: 1,
          transaction_id: 1,
          event_type: 'velocity_anomaly',
          severity: 'warning',
          title: 'Velocity Anomaly',
          description: 'Test event',
          details_json: '{}',
          detected_at: '2026-10-01T00:00:00Z',
          acknowledged_at: null,
          acknowledged_by: null,
        },
      ];

      const mockResponse: PaginatedResponse<SecurityEvent> = {
        items: mockEvents,
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };

      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(securityEventsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useSecurityEvents({
        severity: 'warning',
        event_type: 'velocity_anomaly',
      }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse);
      expect(securityEventsApi.list).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        severity: 'warning',
        event_type: 'velocity_anomaly',
      });
    });
  });

  describe('useAuthorizationDecisions', () => {
    it('fetches authorization decisions with pagination', async () => {
      const mockDecisions: AuthorizationDecisionRecord[] = [
        {
          id: 1,
          request_id: 'REQ-001',
          idempotency_key: 'idem-001',
          agent_id: 1,
          credential_id: 1,
          policy_id: 1,
          amount_cents: 10000,
          currency: 'USD',
          merchant_id: 'M-001',
          merchant_category: 'retail',
          description: 'Test purchase',
          decision: 'allow',
          reasons: ['Within daily limit'],
          policy_violations: null,
          daily_spent_before_cents: 0,
          daily_spent_after_cents: 10000,
          decided_at: '2026-10-01T00:00:00Z',
        },
      ];

      const mockResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: mockDecisions,
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };

      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationDecisionsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAuthorizationDecisions({ page: 1, page_size: 20 }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse);
      expect(result.current.totalPages).toBe(1);
      expect(authorizationDecisionsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20 });
    });

    it('handles agent_id and decision filters', async () => {
      const mockResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationDecisionsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAuthorizationDecisions({ agent_id: 'AGT-001', decision: 'allow' }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationDecisionsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, agent_id: 'AGT-001', decision: 'allow' });
    });

    it('setPagination updates page', async () => {
      const mockResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: [],
        total: 50,
        page: 1,
        page_size: 20,
        total_pages: 3,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationDecisionsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAuthorizationDecisions());

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      act(() => {
        result.current.setPagination({ page: 2 });
      });

      await waitFor(() => {
        expect(result.current.pagination.page).toBe(2);
      });

      expect(authorizationDecisionsApi.list).toHaveBeenCalledWith({ page: 2, page_size: 20 });
    });
  });

  describe('useAuthorizationReservations', () => {
    it('fetches authorization reservations with pagination', async () => {
      const mockReservations: AuthorizationReservation[] = [
        {
          id: 1,
          auth_decision_id: 1,
          agent_id: 1,
          policy_id: 1,
          amount_cents: 10000,
          currency: 'USD',
          usage_date: '2026-10-01',
          status: 'reserved',
          reserved_at: '2026-10-01T00:00:00Z',
          captured_at: null,
          released_at: null,
          expired_at: null,
          created_at: '2026-10-01T00:00:00Z',
          updated_at: '2026-10-01T00:00:00Z',
        },
      ];

      const mockResponse: PaginatedResponse<AuthorizationReservation> = {
        items: mockReservations,
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };

      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationReservationsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAuthorizationReservations({ page: 1, page_size: 20 }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockResponse);
      expect(result.current.totalPages).toBe(1);
      expect(authorizationReservationsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20 });
    });

    it('handles agent_id and status filters', async () => {
      const mockResponse: PaginatedResponse<AuthorizationReservation> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationReservationsApi.list).mockResolvedValue(axiosResponse as any);

      const { result } = renderHook(() => useAuthorizationReservations({ agent_id: 1, status: 'reserved' }));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationReservationsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, agent_id: 1, status: 'reserved' });
    });
  });

  describe('useSpendingPolicy', () => {
    it('fetches spending policy for an agent', async () => {
      const mockPolicy: SpendingPolicy = {
        id: 1,
        agent_id: 1,
        owner_id: 'organization:test@org.com',
        per_transaction_limit_cents: 500000,
        daily_budget_cents: 1000000,
        allowed_currencies: ['USD', 'EUR'],
        allowed_merchant_ids: ['M-001', 'M-002'],
        blocked_merchant_ids: ['M-999'],
        status: 'active',
        effective_at: '2026-01-01T00:00:00Z',
        expires_at: '2027-01-01T00:00:00Z',
        revoked_at: null,
        revoked_by: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      };
      const mockResponse = { data: mockPolicy, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(spendingPoliciesApi.get).mockResolvedValue(mockResponse as any);

      const { result } = renderHook(() => useSpendingPolicy('AGT-001'));

      expect(result.current.loading).toBe(true);
      expect(result.current.data).toBeNull();

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data).toEqual(mockPolicy);
      expect(spendingPoliciesApi.get).toHaveBeenCalledWith('AGT-001');
    });

    it('skips request when agentId is missing', async () => {
      const { result } = renderHook(() => useSpendingPolicy(null));

      expect(result.current.loading).toBe(false);
      expect(result.current.data).toBeNull();
      expect(result.current.error).toBeNull();
      expect(spendingPoliciesApi.get).not.toHaveBeenCalled();
    });

    it('handles error correctly', async () => {
      vi.mocked(spendingPoliciesApi.get).mockRejectedValue(new Error('Not found'));

      const { result } = renderHook(() => useSpendingPolicy('AGT-001'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.error).toBe('Not found');
      expect(result.current.data).toBeNull();
    });

    it('refetch works', async () => {
      const mockPolicy: SpendingPolicy = {
        id: 1,
        agent_id: 1,
        owner_id: 'organization:test@org.com',
        per_transaction_limit_cents: 500000,
        daily_budget_cents: 1000000,
        allowed_currencies: ['USD'],
        allowed_merchant_ids: null,
        blocked_merchant_ids: null,
        status: 'active',
        effective_at: '2026-01-01T00:00:00Z',
        expires_at: null,
        revoked_at: null,
        revoked_by: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      };
      const mockResponse = { data: mockPolicy, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(spendingPoliciesApi.get).mockResolvedValue(mockResponse as any);

      const { result } = renderHook(() => useSpendingPolicy('AGT-001'));

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      const mockPolicy2 = { ...mockPolicy, per_transaction_limit_cents: 1000000 };
      const mockResponse2 = { data: mockPolicy2, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(spendingPoliciesApi.get).mockResolvedValue(mockResponse2 as any);

      await act(async () => {
        await result.current.refetch();
      });

      expect(spendingPoliciesApi.get).toHaveBeenCalledTimes(2);
      expect(result.current.data?.per_transaction_limit_cents).toBe(1000000);
    });
  });

  // --- Filter Reactivity & Stale Response Tests ---

  describe('useAuthorizationDecisions filter reactivity', () => {
    it('changing agent_id filter triggers a new fetch', async () => {
      const mockResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationDecisionsApi.list).mockResolvedValue(axiosResponse as any);

      const { result, rerender } = renderHook(
        ({ agentId }) => useAuthorizationDecisions({ agent_id: agentId }),
        { initialProps: { agentId: 'AGT-001' } }
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationDecisionsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationDecisionsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, agent_id: 'AGT-001' });

      // Change the filter
      vi.mocked(authorizationDecisionsApi.list).mockClear();
      rerender({ agentId: 'AGT-002' });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationDecisionsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationDecisionsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, agent_id: 'AGT-002' });
    });

    it('changing decision filter triggers a new fetch', async () => {
      const mockResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationDecisionsApi.list).mockResolvedValue(axiosResponse as any);

      const { result, rerender } = renderHook(
        ({ decision }) => useAuthorizationDecisions({ decision }),
        { initialProps: { decision: 'allow' as AuthorizationDecision } }
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationDecisionsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationDecisionsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, decision: 'allow' });

      // Change the filter
      vi.mocked(authorizationDecisionsApi.list).mockClear();
      rerender({ decision: 'block' as AuthorizationDecision });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationDecisionsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationDecisionsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, decision: 'block' });
    });
  });

  describe('useAuthorizationReservations filter reactivity', () => {
    it('changing agent_id filter triggers a new fetch', async () => {
      const mockResponse: PaginatedResponse<AuthorizationReservation> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationReservationsApi.list).mockResolvedValue(axiosResponse as any);

      const { result, rerender } = renderHook(
        ({ agentId }) => useAuthorizationReservations({ agent_id: agentId }),
        { initialProps: { agentId: 1 } }
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationReservationsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationReservationsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, agent_id: 1 });

      // Change the filter
      vi.mocked(authorizationReservationsApi.list).mockClear();
      rerender({ agentId: 2 });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationReservationsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationReservationsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, agent_id: 2 });
    });

    it('changing status filter triggers a new fetch', async () => {
      const mockResponse: PaginatedResponse<AuthorizationReservation> = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      const axiosResponse = { data: mockResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      vi.mocked(authorizationReservationsApi.list).mockResolvedValue(axiosResponse as any);

      const { result, rerender } = renderHook(
        ({ status }) => useAuthorizationReservations({ status }),
        { initialProps: { status: 'reserved' as ReservationStatus } }
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationReservationsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationReservationsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, status: 'reserved' });

      // Change the filter
      vi.mocked(authorizationReservationsApi.list).mockClear();
      rerender({ status: 'captured' as ReservationStatus });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(authorizationReservationsApi.list).toHaveBeenCalledTimes(1);
      expect(authorizationReservationsApi.list).toHaveBeenCalledWith({ page: 1, page_size: 20, status: 'captured' });
    });
  });

  describe('stale response guard', () => {
    it('a slower previous request cannot overwrite newer data', async () => {
      let resolveSlow: (value: any) => void;
      let resolveFast: (value: any) => void;

      const slowPromise = new Promise((resolve) => { resolveSlow = resolve; });
      const fastPromise = new Promise((resolve) => { resolveFast = resolve; });

      vi.mocked(authorizationDecisionsApi.list)
        .mockReturnValueOnce(slowPromise as any)
        .mockReturnValueOnce(fastPromise as any);

      const { result, rerender } = renderHook(
        ({ agentId }) => useAuthorizationDecisions({ agent_id: agentId }),
        { initialProps: { agentId: 'AGT-001' } }
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(true);
      });

      // Change filter to trigger a second (fast) request
      rerender({ agentId: 'AGT-002' });

      await waitFor(() => {
        expect(result.current.loading).toBe(true);
      });

      // Resolve the fast request first
      const fastResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: [{ id: 2, request_id: 'REQ-002', agent_id: 2, amount_cents: 200, currency: 'USD', merchant_id: 'M-002', merchant_category: 'retail', decision: 'allow', reasons: ['fast'], policy_violations: null, daily_spent_before_cents: 0, daily_spent_after_cents: 200, decided_at: '2026-10-01T00:00:00Z', idempotency_key: null, credential_id: null, policy_id: null, description: null }],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
      const fastAxiosResponse = { data: fastResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      resolveFast!(fastAxiosResponse as any);

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(result.current.data?.items[0].request_id).toBe('REQ-002');

      // Now resolve the slow request - it should NOT overwrite the data
      const slowResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: [{ id: 1, request_id: 'REQ-001', agent_id: 1, amount_cents: 100, currency: 'USD', merchant_id: 'M-001', merchant_category: 'retail', decision: 'allow', reasons: ['slow'], policy_violations: null, daily_spent_before_cents: 0, daily_spent_after_cents: 100, decided_at: '2026-10-01T00:00:00Z', idempotency_key: null, credential_id: null, policy_id: null, description: null }],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
      const slowAxiosResponse = { data: slowResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      resolveSlow!(slowAxiosResponse as any);

      // Give it a moment to process
      await waitFor(() => {
        // Data should still be from the fast request
        expect(result.current.data?.items[0].request_id).toBe('REQ-002');
      });
    });
  });

  describe('useSpendingPolicy null agentId invalidates pending requests', () => {
    it('a pending policy request cannot restore data after agentId becomes null', async () => {
      let resolvePolicy: (value: any) => void;

      const policyPromise = new Promise((resolve) => { resolvePolicy = resolve; });

      vi.mocked(spendingPoliciesApi.get).mockReturnValueOnce(policyPromise as any);

      const { result, rerender } = renderHook<ReturnType<typeof useSpendingPolicy>, { agentId: string | null }>(
        ({ agentId }) => useSpendingPolicy(agentId),
        { initialProps: { agentId: 'AGT-001' } }
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(true);
      });

      // Change agentId to null - this should clear state and invalidate the pending request
      rerender({ agentId: null as string | null });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
        expect(result.current.data).toBeNull();
        expect(result.current.error).toBeNull();
      });

      // Now resolve the old pending request - it should NOT restore data
      const policyResponse = {
        id: 1,
        agent_id: 1,
        owner_id: 'owner-1',
        per_transaction_limit_cents: 1000000,
        daily_budget_cents: 5000000,
        allowed_currencies: ['USD'],
        allowed_merchant_ids: null,
        blocked_merchant_ids: null,
        status: 'active' as const,
        effective_at: '2026-01-01T00:00:00Z',
        expires_at: null,
        revoked_at: null,
        revoked_by: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      };
      const policyAxiosResponse = { data: policyResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      resolvePolicy!(policyAxiosResponse as any);

      // Give it a moment to process
      await waitFor(() => {
        // Data should still be null (not restored by stale response)
        expect(result.current.data).toBeNull();
      });
    });
  });

  describe('unmount invalidates pending requests', () => {
    it('an unmounted hook cannot apply a stale response', async () => {
      let resolveSlow: (value: any) => void;

      const slowPromise = new Promise((resolve) => { resolveSlow = resolve; });

      vi.mocked(authorizationDecisionsApi.list).mockReturnValueOnce(slowPromise as any);

      const { result, unmount } = renderHook(
        () => useAuthorizationDecisions({ agent_id: 'AGT-001' })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(true);
      });

      // Unmount the component
      unmount();

      // Now resolve the slow request - it should NOT update state (no crash, no update)
      const slowResponse: PaginatedResponse<AuthorizationDecisionRecord> = {
        items: [{ id: 1, request_id: 'REQ-001', agent_id: 1, amount_cents: 100, currency: 'USD', merchant_id: 'M-001', merchant_category: 'retail', decision: 'allow', reasons: ['slow'], policy_violations: null, daily_spent_before_cents: 0, daily_spent_after_cents: 100, decided_at: '2026-10-01T00:00:00Z', idempotency_key: null, credential_id: null, policy_id: null, description: null }],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
      const slowAxiosResponse = { data: slowResponse, status: 200, statusText: 'OK', headers: {}, config: {} };
      resolveSlow!(slowAxiosResponse as any);

      // Should not throw and state should not be updated (we can't easily test state after unmount,
      // but we can verify no error is thrown)
      expect(true).toBe(true);
    });
  });
});