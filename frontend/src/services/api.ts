/** API client for AgentGuard backend */

import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import type {
  Agent,
  AgentDetail,
  Transaction,
  TransactionDetail,
  SecurityEvent,
  DashboardSummary,
  HealthResponse,
  PaginatedResponse,
  PaginationParams,
  AuthorizationDecisionRecord,
  AuthorizationReservation,
  SpendingPolicy,
} from '../types';

// Development always uses Vite's same-origin proxy. This avoids stale or
// production-oriented VITE_API_BASE_URL values in the repository .env.
const API_BASE_URL = import.meta.env.DEV ? '/api' : (import.meta.env.VITE_API_BASE_URL || '/api');
const PUBLIC_DEMO_MODE = import.meta.env.VITE_PUBLIC_DEMO_MODE === 'true';
const READINESS_BUDGET_MS = 90_000;
const READINESS_DELAYS_MS = [0, 2_000, 4_000, 8_000, 12_000, 15_000, 15_000, 15_000];

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

let readinessWait: Promise<void> | null = null;

function isRetryableReadinessError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false;
  const status = error.response?.status;
  return !status || status === 408 || status === 502 || status === 503 || status === 504 || error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT';
}

function delay(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, ms));
}

async function waitForReadiness(deadline: number): Promise<void> {
  if (readinessWait) return readinessWait;
  readinessWait = (async () => {
    for (const pause of READINESS_DELAYS_MS) {
      if (Date.now() >= deadline) throw new Error('AgentGuard server did not become ready in time');
      if (pause) await delay(pause);
      try {
        await api.get('/health', { timeout: 10_000 });
        return;
      } catch (error) {
        if (!isRetryableReadinessError(error)) throw error;
      }
    }
    throw new Error('AgentGuard server did not become ready in time');
  })().finally(() => { readinessWait = null; });
  return readinessWait;
}

export async function readOnlyGet<T>(request: () => Promise<T>): Promise<T> {
  const deadline = Date.now() + READINESS_BUDGET_MS;
  while (true) {
    try {
      return await request();
    } catch (error) {
      if (!isRetryableReadinessError(error)) throw error;
      if (Date.now() >= deadline) throw error;
      await waitForReadiness(deadline);
      if (Date.now() < deadline) await delay(1_000);
    }
  }
}

// Request interceptor for logging
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    if (PUBLIC_DEMO_MODE && config.method?.toLowerCase() === 'get' && config.url?.startsWith('/')) {
      config.url = `/public-demo${config.url}`;
    }
    if (PUBLIC_DEMO_MODE && config.url === '/attack-simulator/run') {
      config.url = '/public-demo/attack-simulator/run';
    }
    console.debug(`[API] ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const message = error.response?.data as { detail?: string } | undefined;
    console.error(`[API Error] ${error.config?.method?.toUpperCase()} ${error.config?.url}:`, message?.detail || error.message);
    return Promise.reject(error);
  }
);

// Health
export const healthApi = {
  check: () => readOnlyGet(() => api.get<HealthResponse>('/health')),
};

// Agents
export const agentsApi = {
  list: (params?: Partial<PaginationParams> & { status?: string }) =>
    readOnlyGet(() => api.get<PaginatedResponse<Agent>>('/agents', { params })),

  get: (id: number) => readOnlyGet(() => api.get<AgentDetail>(`/agents/${id}`)),

  getByAgentId: (agentId: string) => readOnlyGet(() => api.get<AgentDetail>(`/agents/by-agent-id/${agentId}`)),
};

// Transactions
export const transactionsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: number;
    status?: string;
    min_risk?: number;
    max_risk?: number;
  }) => readOnlyGet(() => api.get<PaginatedResponse<Transaction>>('/transactions', { params })),

  get: (id: number) => readOnlyGet(() => api.get<TransactionDetail>(`/transactions/${id}`)),
};

// Dashboard
export const dashboardApi = {
  summary: () => readOnlyGet(() => api.get<DashboardSummary>('/dashboard/summary')),
};

// Security Events
export const securityEventsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: number;
    transaction_id?: number;
    event_type?: string;
    severity?: string;
  }) => readOnlyGet(() => api.get<PaginatedResponse<SecurityEvent>>('/security-events', { params })),
};

// Authorization Decisions
export const authorizationDecisionsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: string;
    decision?: string;
  }) => readOnlyGet(() => api.get<PaginatedResponse<AuthorizationDecisionRecord>>('/authorize/decisions', { params })),

  get: (requestId: string) => readOnlyGet(() => api.get<AuthorizationDecisionRecord>(`/authorize/decisions/${requestId}`)),
};

// Authorization Reservations
export const authorizationReservationsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: number;
    status?: string;
  }) => readOnlyGet(() => api.get<PaginatedResponse<AuthorizationReservation>>('/authorize/reservations', { params })),

  get: (authDecisionId: number) => readOnlyGet(() => api.get<AuthorizationReservation>(`/authorize/reservations/${authDecisionId}`)),
};

// Spending Policies
export const spendingPoliciesApi = {
  get: (agentId: string) => readOnlyGet(() => api.get<SpendingPolicy>(`/policies/${agentId}`)),
};

export default api;
