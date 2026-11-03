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

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

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
  check: () => api.get<HealthResponse>('/health'),
};

// Agents
export const agentsApi = {
  list: (params?: Partial<PaginationParams> & { status?: string }) =>
    api.get<PaginatedResponse<Agent>>('/agents', { params }),

  get: (id: number) => api.get<AgentDetail>(`/agents/${id}`),

  getByAgentId: (agentId: string) => api.get<AgentDetail>(`/agents/by-agent-id/${agentId}`),
};

// Transactions
export const transactionsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: number;
    status?: string;
    min_risk?: number;
    max_risk?: number;
  }) => api.get<PaginatedResponse<Transaction>>('/transactions', { params }),

  get: (id: number) => api.get<TransactionDetail>(`/transactions/${id}`),
};

// Dashboard
export const dashboardApi = {
  summary: () => api.get<DashboardSummary>('/dashboard/summary'),
};

// Security Events
export const securityEventsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: number;
    transaction_id?: number;
    event_type?: string;
    severity?: string;
  }) => api.get<PaginatedResponse<SecurityEvent>>('/security-events', { params }),
};

// Authorization Decisions
export const authorizationDecisionsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: string;
    decision?: string;
  }) => api.get<PaginatedResponse<AuthorizationDecisionRecord>>('/authorize/decisions', { params }),

  get: (requestId: string) => api.get<AuthorizationDecisionRecord>(`/authorize/decisions/${requestId}`),
};

// Authorization Reservations
export const authorizationReservationsApi = {
  list: (params?: Partial<PaginationParams> & {
    agent_id?: number;
    status?: string;
  }) => api.get<PaginatedResponse<AuthorizationReservation>>('/authorize/reservations', { params }),

  get: (authDecisionId: number) => api.get<AuthorizationReservation>(`/authorize/reservations/${authDecisionId}`),
};

// Spending Policies
export const spendingPoliciesApi = {
  get: (agentId: string) => api.get<SpendingPolicy>(`/policies/${agentId}`),
};

export default api;
