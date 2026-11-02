/** Custom hooks for API data fetching with loading, error, and retry states */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { PaginatedResponse, PaginationParams } from '../types';
import {
  agentsApi,
  transactionsApi,
  dashboardApi,
  healthApi,
  securityEventsApi,
  authorizationDecisionsApi,
  authorizationReservationsApi,
  spendingPoliciesApi,
} from '../services/api';

interface UseApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

interface UsePaginatedApiState<T> extends UseApiState<PaginatedResponse<T>> {
  pagination: PaginationParams;
  setPagination: (params: Partial<PaginationParams>) => void;
  totalPages: number;
}

export function useHealth(): UseApiState<{ status: string; version: string; database: string }> {
  const [data, setData] = useState<{ status: string; version: string; database: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await healthApi.check();
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch health');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  return { data, loading, error, refetch: fetchHealth };
}

export function useDashboardSummary(): UseApiState<DashboardSummary> {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await dashboardApi.summary();
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch dashboard summary');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  return { data, loading, error, refetch: fetchSummary };
}

export function useAgents(initialParams?: Partial<PaginationParams> & { status?: string }): UsePaginatedApiState<Agent> {
  const [data, setData] = useState<PaginatedResponse<Agent> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPaginationState] = useState<PaginationParams>({
    page: initialParams?.page || 1,
    page_size: initialParams?.page_size || 20,
  });

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params = { ...pagination };
      if (initialParams?.status) {
        (params as any).status = initialParams.status;
      }
      const response = await agentsApi.list(params);
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch agents');
    } finally {
      setLoading(false);
    }
  }, [pagination.page, pagination.page_size, initialParams?.status]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const setPagination = useCallback((params: Partial<PaginationParams>) => {
    setPaginationState(prev => ({ ...prev, ...params }));
  }, []);

  return {
    data,
    loading,
    error,
    refetch: fetchAgents,
    pagination,
    setPagination,
    totalPages: data?.total_pages || 0,
  };
}

export function useAgent(id: number | null): UseApiState<AgentDetail> {
  const [data, setData] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAgent = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const response = await agentsApi.get(id);
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch agent');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchAgent();
  }, [fetchAgent]);

  return { data, loading, error, refetch: fetchAgent };
}

interface TransactionListParams extends PaginationParams {
  agent_id?: number;
  status?: string;
  min_risk?: number;
  max_risk?: number;
}

export function useTransactions(
  initialParams?: Partial<TransactionListParams>
): UsePaginatedApiState<Transaction> {
  const [data, setData] = useState<PaginatedResponse<Transaction> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPaginationState] = useState<PaginationParams>({
    page: initialParams?.page || 1,
    page_size: initialParams?.page_size || 20,
  });

  const fetchTransactions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params: TransactionListParams = { ...pagination };
      if (initialParams?.agent_id) params.agent_id = initialParams.agent_id;
      if (initialParams?.status) params.status = initialParams.status;
      if (initialParams?.min_risk !== undefined) params.min_risk = initialParams.min_risk;
      if (initialParams?.max_risk !== undefined) params.max_risk = initialParams.max_risk;

      const response = await transactionsApi.list(params);
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch transactions');
    } finally {
      setLoading(false);
    }
  }, [pagination.page, pagination.page_size, initialParams?.agent_id, initialParams?.status, initialParams?.min_risk, initialParams?.max_risk]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const setPagination = useCallback((params: Partial<PaginationParams>) => {
    setPaginationState(prev => ({ ...prev, ...params }));
  }, []);

  return {
    data,
    loading,
    error,
    refetch: fetchTransactions,
    pagination,
    setPagination,
    totalPages: data?.total_pages || 0,
  };
}

export function useTransaction(id: number | null): UseApiState<TransactionDetail> {
  const [data, setData] = useState<TransactionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTransaction = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      setError(null);
      const response = await transactionsApi.get(id);
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch transaction');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchTransaction();
  }, [fetchTransaction]);

  return { data, loading, error, refetch: fetchTransaction };
}

// Import the DashboardSummary type
import type {
  DashboardSummary,
  Agent,
  Transaction,
  AgentDetail,
  TransactionDetail,
  SecurityEvent,
  AuthorizationDecisionRecord,
  AuthorizationReservation,
  SpendingPolicy,
  AuthorizationDecision,
  ReservationStatus,
} from '../types';

interface SecurityEventListParams extends PaginationParams {
  agent_id?: number;
  transaction_id?: number;
  event_type?: string;
  severity?: string;
}

export function useSecurityEvents(
  initialParams?: Partial<SecurityEventListParams>
): UsePaginatedApiState<SecurityEvent> {
  const [data, setData] = useState<PaginatedResponse<SecurityEvent> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPaginationState] = useState<PaginationParams>({
    page: initialParams?.page || 1,
    page_size: initialParams?.page_size || 20,
  });

  const fetchSecurityEvents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params: SecurityEventListParams = { ...pagination };
      if (initialParams?.agent_id) params.agent_id = initialParams.agent_id;
      if (initialParams?.transaction_id) params.transaction_id = initialParams.transaction_id;
      if (initialParams?.event_type) params.event_type = initialParams.event_type;
      if (initialParams?.severity) params.severity = initialParams.severity;

      const response = await securityEventsApi.list(params);
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch security events');
    } finally {
      setLoading(false);
    }
  }, [pagination.page, pagination.page_size, initialParams?.agent_id, initialParams?.transaction_id, initialParams?.event_type, initialParams?.severity]);

  useEffect(() => {
    fetchSecurityEvents();
  }, [fetchSecurityEvents]);

  const setPagination = useCallback((params: Partial<PaginationParams>) => {
    setPaginationState(prev => ({ ...prev, ...params }));
  }, []);

  return {
    data,
    loading,
    error,
    refetch: fetchSecurityEvents,
    pagination,
    setPagination,
    totalPages: data?.total_pages || 0,
  };
}

interface AuthorizationDecisionListParams extends PaginationParams {
  agent_id?: string;
  decision?: AuthorizationDecision;
}

export function useAuthorizationDecisions(
  initialParams?: Partial<AuthorizationDecisionListParams>
): UsePaginatedApiState<AuthorizationDecisionRecord> {
  const [data, setData] = useState<PaginatedResponse<AuthorizationDecisionRecord> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPaginationState] = useState<PaginationParams>({
    page: initialParams?.page || 1,
    page_size: initialParams?.page_size || 20,
  });
  const requestIdRef = useRef(0);

  const fetchAuthorizationDecisions = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    try {
      setLoading(true);
      setError(null);
      const params: AuthorizationDecisionListParams = { ...pagination };
      if (initialParams?.agent_id) params.agent_id = initialParams.agent_id;
      if (initialParams?.decision) params.decision = initialParams.decision;

      const response = await authorizationDecisionsApi.list(params);
      // Stale response guard: only update if this is still the latest request
      if (currentRequestId === requestIdRef.current) {
        setData(response.data);
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch authorization decisions');
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [pagination.page, pagination.page_size, initialParams?.agent_id, initialParams?.decision]);

  useEffect(() => {
    fetchAuthorizationDecisions();
    // Invalidate pending requests on unmount
    return () => { requestIdRef.current++; };
  }, [fetchAuthorizationDecisions]);

  const setPagination = useCallback((params: Partial<PaginationParams>) => {
    setPaginationState(prev => ({ ...prev, ...params }));
  }, []);

  return {
    data,
    loading,
    error,
    refetch: fetchAuthorizationDecisions,
    pagination,
    setPagination,
    totalPages: data?.total_pages || 0,
  };
}

interface AuthorizationReservationListParams extends PaginationParams {
  agent_id?: number;
  status?: ReservationStatus;
}

export function useAuthorizationReservations(
  initialParams?: Partial<AuthorizationReservationListParams>
): UsePaginatedApiState<AuthorizationReservation> {
  const [data, setData] = useState<PaginatedResponse<AuthorizationReservation> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPaginationState] = useState<PaginationParams>({
    page: initialParams?.page || 1,
    page_size: initialParams?.page_size || 20,
  });
  const requestIdRef = useRef(0);

  const fetchAuthorizationReservations = useCallback(async () => {
    const currentRequestId = ++requestIdRef.current;
    try {
      setLoading(true);
      setError(null);
      const params: AuthorizationReservationListParams = { ...pagination };
      if (initialParams?.agent_id) params.agent_id = initialParams.agent_id;
      if (initialParams?.status) params.status = initialParams.status;

      const response = await authorizationReservationsApi.list(params);
      // Stale response guard: only update if this is still the latest request
      if (currentRequestId === requestIdRef.current) {
        setData(response.data);
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch authorization reservations');
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [pagination.page, pagination.page_size, initialParams?.agent_id, initialParams?.status]);

  useEffect(() => {
    fetchAuthorizationReservations();
    // Invalidate pending requests on unmount
    return () => { requestIdRef.current++; };
  }, [fetchAuthorizationReservations]);

  const setPagination = useCallback((params: Partial<PaginationParams>) => {
    setPaginationState(prev => ({ ...prev, ...params }));
  }, []);

  return {
    data,
    loading,
    error,
    refetch: fetchAuthorizationReservations,
    pagination,
    setPagination,
    totalPages: data?.total_pages || 0,
  };
}

export function useSpendingPolicy(agentId: string | null): UseApiState<SpendingPolicy> {
  const [data, setData] = useState<SpendingPolicy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const fetchSpendingPolicy = useCallback(async () => {
    if (!agentId) {
      // Invalidate any in-flight requests by incrementing the request counter
      requestIdRef.current++;
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    const currentRequestId = ++requestIdRef.current;
    try {
      setLoading(true);
      setError(null);
      const response = await spendingPoliciesApi.get(agentId);
      // Stale response guard: only update if this is still the latest request
      if (currentRequestId === requestIdRef.current) {
        setData(response.data);
      }
    } catch (err) {
      if (currentRequestId === requestIdRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch spending policy');
      }
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [agentId]);

  useEffect(() => {
    fetchSpendingPolicy();
    // Invalidate pending requests on unmount
    return () => { requestIdRef.current++; };
  }, [fetchSpendingPolicy]);

  return { data, loading, error, refetch: fetchSpendingPolicy };
}