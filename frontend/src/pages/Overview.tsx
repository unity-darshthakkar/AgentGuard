/** Overview dashboard page */

import { Users, CreditCard, ShieldCheck, DollarSign, TrendingUp, Activity } from 'lucide-react';
import { useDashboardSummary } from '../hooks/useApi';
import { KPICard } from '../components/ui/KPICard';
import { ErrorState, LoadingState } from '../components/ui/States';
import { formatCurrency, formatNumber } from '../utils/formatters';
import { useNavigate } from 'react-router-dom';

export function Overview() {
  const navigate = useNavigate();
  const { data, loading, error, refetch } = useDashboardSummary();

  const kpis = data ? [
    {
      title: 'Total Agents',
      value: formatNumber(data.total_agents),
      subtitle: `${data.active_agents} active, ${data.suspended_agents} suspended`,
      icon: <Users className="w-6 h-6" />,
      iconBg: 'bg-primary-100',
      iconColor: 'text-primary-600',
    },
    {
      title: 'Total Transactions',
      value: formatNumber(data.total_transactions),
      subtitle: `${data.approved_transactions} approved, ${data.blocked_transactions} blocked, ${data.under_review_transactions} under review`,
      icon: <CreditCard className="w-6 h-6" />,
      iconBg: 'bg-success-100',
      iconColor: 'text-success-600',
    },
    {
      title: 'Transaction Volume',
      value: formatCurrency(data.total_volume_usd),
      subtitle: `Avg risk score: ${data.avg_risk_score.toFixed(1)}`,
      icon: <DollarSign className="w-6 h-6" />,
      iconBg: 'bg-warning-100',
      iconColor: 'text-warning-600',
    },
    {
      title: 'Security Events',
      value: formatNumber(data.recent_security_events),
      subtitle: `${data.unacknowledged_events} unacknowledged (all time), ${data.recent_security_events} in last 24h`,
      icon: <ShieldCheck className="w-6 h-6" />,
      iconBg: 'bg-danger-100',
      iconColor: 'text-danger-600',
    },
  ] : [];

  if (loading) {
    return (
      <LoadingState message="Loading dashboard..." />
    );
  }

  if (error) {
    return (
      <ErrorState message={error} onRetry={refetch} />
    );
  }

  return (
    <>
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {kpis.map((kpi, index) => (
          <KPICard key={index} {...kpi} />
        ))}
      </div>

      {/* Secondary Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="card p-6">
          <h3 className="text-lg font-medium text-secondary-900 mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary-600" />
            Transaction Status Breakdown
          </h3>
          <div className="space-y-3">
            {data && [
              { label: 'Approved', value: data.approved_transactions, total: data.total_transactions, color: 'success' },
              { label: 'Blocked', value: data.blocked_transactions, total: data.total_transactions, color: 'danger' },
              { label: 'Under Review', value: data.under_review_transactions, total: data.total_transactions, color: 'warning' },
              { label: 'Pending', value: data.pending_transactions, total: data.total_transactions, color: 'primary' },
              { label: 'Failed', value: data.failed_transactions, total: data.total_transactions, color: 'danger' },
            ].map((item, i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full bg-${item.color}-500`} />
                  <span className="text-sm text-secondary-600">{item.label}</span>
                </div>
                <div className="text-right">
                  <span className="font-medium text-secondary-900">{formatNumber(item.value)}</span>
                  <span className="text-sm text-secondary-500 ml-2">({((item.value / item.total) * 100).toFixed(1)}%)</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6 lg:col-span-2">
          <h3 className="text-lg font-medium text-secondary-900 mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary-600" />
            Risk Distribution
          </h3>
          <div className="space-y-3">
            {data && [
              { label: 'Critical (90-100)', value: data.critical_risk_transactions, color: 'danger' },
              { label: 'High (70-89)', value: data.high_risk_transactions, color: 'orange' },
              { label: 'Medium (31-69)', value: data.medium_risk_transactions, color: 'warning' },
              { label: 'Low (0-30)', value: data.low_risk_transactions, color: 'success' },
            ].map((item, i) => {
              const percentage = data.total_transactions > 0 ? (item.value / data.total_transactions) * 100 : 0;
              return (
                <div key={i} className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full bg-${item.color}-500 flex-shrink-0`} />
                  <span className="text-sm text-secondary-600 w-32">{item.label}</span>
                  <div className="flex-1 h-2 bg-secondary-200 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full bg-${item.color}-500 transition-all duration-500`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium text-secondary-900 w-20 text-right">
                    {formatNumber(item.value)} ({percentage.toFixed(1)}%)
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Agent Status Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-6">
          <h3 className="text-lg font-medium text-secondary-900 mb-4 flex items-center gap-2">
            <Users className="w-5 h-5 text-primary-600" />
            Agent Status Overview
          </h3>
          {data && (
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-success-50 rounded-xl">
                <p className="text-3xl font-bold text-success-600">{data.active_agents}</p>
                <p className="text-sm text-secondary-500">Active</p>
              </div>
              <div className="p-4 bg-danger-50 rounded-xl">
                <p className="text-3xl font-bold text-danger-600">{data.suspended_agents}</p>
                <p className="text-sm text-secondary-500">Suspended</p>
              </div>
              <div className="p-4 bg-warning-50 rounded-xl">
                <p className="text-3xl font-bold text-warning-600">{data.pending_review_agents}</p>
                <p className="text-sm text-secondary-500">Pending Review</p>
              </div>
              <div className="p-4 bg-secondary-50 rounded-xl">
                <p className="text-3xl font-bold text-secondary-600">{data.total_agents}</p>
                <p className="text-sm text-secondary-500">Total</p>
              </div>
            </div>
          )}
        </div>

        <div className="card p-6">
          <h3 className="text-lg font-medium text-secondary-900 mb-4 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-primary-600" />
            Quick Actions
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <button className="btn-secondary text-left p-4 hover:bg-primary-50 border-primary-200" onClick={() => navigate('/agents')}>
              <Users className="w-5 h-5 text-primary-600 mb-2" />
              <p className="font-medium text-secondary-900">View All Agents</p>
              <p className="text-xs text-secondary-500">Manage agent registry</p>
              <span className="badge badge-info mt-1 inline-block">Open registry</span>
            </button>
            <button className="btn-secondary text-left p-4 hover:bg-primary-50 border-primary-200" onClick={() => navigate('/transactions')}>
              <CreditCard className="w-5 h-5 text-primary-600 mb-2" />
              <p className="font-medium text-secondary-900">Monitor Transactions</p>
              <p className="text-xs text-secondary-500">Review payment activity</p>
              <span className="badge badge-info mt-1 inline-block">Open monitor</span>
            </button>
            <button className="btn-secondary text-left p-4 hover:bg-primary-50 border-primary-200" onClick={() => navigate('/security-events')}>
              <ShieldCheck className="w-5 h-5 text-primary-600 mb-2" />
              <p className="font-medium text-secondary-900">Security Events</p>
              <p className="text-xs text-secondary-500">Investigate alerts</p>
              <span className="badge badge-info mt-1 inline-block">Open events</span>
            </button>
            <button className="btn-secondary text-left p-4 hover:bg-primary-50 border-primary-200" onClick={() => navigate('/attack-simulator')}>
              <TrendingUp className="w-5 h-5 text-primary-600 mb-2" />
              <p className="font-medium text-secondary-900">Risk Analytics</p>
              <p className="text-xs text-secondary-500">View risk trends</p>
              <span className="badge badge-info mt-1 inline-block">Run simulator</span>
            </button>
          </div>
        </div>
      </div>

      {/* Demo Notice */}
      <div className="mt-6 p-4 bg-primary-50 border border-primary-200 rounded-xl">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center flex-shrink-0">
            <Activity className="w-5 h-5 text-primary-600" />
          </div>
          <div>
            <p className="font-medium text-primary-800">Synthetic Demonstration Data</p>
            <p className="text-sm text-primary-600 mt-1">
              All data shown is generated for demonstration purposes. No real agent authentication,
              Some dashboard records are synthetic. PayPal execution remains behind the secured checkout flow.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
