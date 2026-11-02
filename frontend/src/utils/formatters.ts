/** Utility functions for formatting */

import { format, formatDistanceToNow, parseISO } from 'date-fns';

export function formatCurrency(amount: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat('en-US').format(num);
}

export function formatPercentage(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`;
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  try {
    const date = parseISO(dateString);
    return format(date, 'MMM d, yyyy HH:mm');
  } catch {
    return 'Invalid date';
  }
}

export function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return '—';
  try {
    const date = parseISO(dateString);
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return 'Invalid date';
  }
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return `${str.slice(0, length)}...`;
}

export function parseJsonSafe<T>(json: string | null | undefined, fallback: T): T {
  if (!json) return fallback;
  try {
    return JSON.parse(json) as T;
  } catch {
    return fallback;
  }
}

export function getInitials(name: string): string {
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export function getRiskLevel(score: number): 'low' | 'medium' | 'high' | 'critical' {
  if (score <= 30) return 'low';
  if (score <= 60) return 'medium';
  if (score <= 85) return 'high';
  return 'critical';
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
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
  return colors[status] || 'bg-secondary-100 text-secondary-600';
}

export function getSeverityColor(severity: string): string {
  const colors: Record<string, string> = {
    info: 'bg-primary-100 text-primary-600',
    warning: 'bg-warning-100 text-warning-600',
    critical: 'bg-danger-100 text-danger-600',
  };
  return colors[severity] || 'bg-secondary-100 text-secondary-600';
}