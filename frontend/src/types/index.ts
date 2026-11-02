/** TypeScript types for AgentGuard frontend */

export type AgentStatus = 'active' | 'suspended' | 'pending_review' | 'decommissioned';
export type TransactionStatus = 'approved' | 'blocked' | 'under_review' | 'pending' | 'failed';
export type SecurityEventType = 'velocity_anomaly' | 'geo_anomaly' | 'amount_outlier' | 'new_merchant' | 'permission_violation' | 'pattern_deviation';
export type SecurityEventSeverity = 'info' | 'warning' | 'critical';
export type AuthorizationDecision = 'allow' | 'block' | 'review';
export type ReservationStatus = 'reserved' | 'captured' | 'released' | 'expired';
export type PolicyStatus = 'active' | 'revoked' | 'expired';

export interface PaginationParams {
  page: number;
  page_size: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Agent {
  id: number;
  agent_id: string;
  name: string;
  description: string | null;
  status: AgentStatus;
  owner_type: string;
  owner_name: string;
  owner_email: string;
  owner_contact: string | null;
  daily_limit_usd: number;
  monthly_limit_usd: number;
  allowed_merchant_categories: string | null;
  blocked_merchant_categories: string | null;
  created_at: string;
  updated_at: string;
  last_active_at: string | null;
}

export interface AgentDetail extends Agent {
  transaction_count: number;
  approved_count: number;
  blocked_count: number;
  under_review_count: number;
  total_volume_usd: number;
  avg_risk_score: number;
}

export interface Transaction {
  id: number;
  transaction_id: string;
  agent_id: number;
  amount_usd: number;
  currency: string;
  merchant_name: string;
  merchant_category: string;
  merchant_country: string;
  description: string | null;
  status: TransactionStatus;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  decision_reason: string | null;
  requested_at: string;
  decided_at: string | null;
  completed_at: string | null;
}

export interface TransactionDetail extends Transaction {
  agent?: Agent;
  security_events: SecurityEvent[];
}

export interface SecurityEvent {
  id: number;
  event_id: string;
  agent_id: number;
  transaction_id: number | null;
  event_type: SecurityEventType;
  severity: SecurityEventSeverity;
  title: string;
  description: string | null;
  details_json: string | null;
  detected_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
}

export interface AuthorizationDecisionRecord {
  id: number;
  request_id: string;
  idempotency_key: string | null;
  agent_id: number;
  credential_id: number | null;
  policy_id: number | null;
  amount_cents: number;
  currency: string;
  merchant_id: string;
  merchant_category: string;
  description: string | null;
  decision: AuthorizationDecision;
  reasons: string[];
  policy_violations: string[] | null;
  daily_spent_before_cents: number;
  daily_spent_after_cents: number;
  decided_at: string;
}

export interface AuthorizationReservation {
  id: number;
  auth_decision_id: number;
  agent_id: number;
  policy_id: number | null;
  amount_cents: number;
  currency: string;
  usage_date: string;
  status: ReservationStatus;
  reserved_at: string;
  captured_at: string | null;
  released_at: string | null;
  expired_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SpendingPolicy {
  id: number;
  agent_id: number;
  owner_id: string;
  per_transaction_limit_cents: number;
  daily_budget_cents: number;
  allowed_currencies: string[];
  allowed_merchant_ids: string[] | null;
  blocked_merchant_ids: string[] | null;
  status: PolicyStatus;
  effective_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  revoked_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface DashboardSummary {
  total_agents: number;
  active_agents: number;
  suspended_agents: number;
  pending_review_agents: number;
  total_transactions: number;
  approved_transactions: number;
  blocked_transactions: number;
  under_review_transactions: number;
  pending_transactions: number;
  failed_transactions: number;
  total_volume_usd: number;
  avg_risk_score: number;
  // Risk distribution buckets (mutually exclusive, covering 0-100)
  low_risk_transactions: number;      // 0-30
  medium_risk_transactions: number;   // 31-69
  high_risk_transactions: number;     // 70-89
  critical_risk_transactions: number; // 90-100
  recent_security_events: number;
  unacknowledged_events: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  timestamp: string;
}

export interface ApiError {
  detail: string;
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export const RISK_LEVEL_COLORS: Record<RiskLevel, string> = {
  low: 'bg-success-100 text-success-600',
  medium: 'bg-warning-100 text-warning-600',
  high: 'bg-orange-100 text-orange-600',
  critical: 'bg-danger-100 text-danger-600',
};

export const STATUS_COLORS: Record<AgentStatus | TransactionStatus, string> = {
  active: 'bg-success-100 text-success-600',
  suspended: 'bg-danger-100 text-danger-600',
  pending_review: 'bg-warning-100 text-warning-600',
  decommissioned: 'bg-secondary-100 text-secondary-600',
  approved: 'bg-success-100 text-success-600',
  blocked: 'bg-danger-100 text-danger-600',
  under_review: 'bg-warning-100 text-warning-600',
  pending: 'bg-primary-100 text-primary-600',
  failed: 'bg-danger-100 text-danger-600',
};

export const SEVERITY_COLORS: Record<SecurityEventSeverity, string> = {
  info: 'bg-primary-100 text-primary-600',
  warning: 'bg-warning-100 text-warning-600',
  critical: 'bg-danger-100 text-danger-600',
};