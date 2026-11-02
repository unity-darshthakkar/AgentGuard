/** Transaction Detail Panel with risk signals */

import { X, ChevronDown, ChevronUp, AlertTriangle, Shield, DollarSign, User, CreditCard, Globe } from 'lucide-react';
import { useState } from 'react';
import type { Transaction, TransactionDetail, SecurityEvent } from '../../types';
import { formatCurrency, formatDate, getStatusColor, getSeverityColor, parseJsonSafe } from '../../utils/formatters';

// TransactionWithDetails extends Transaction with optional agent and security_events
type TransactionWithDetails = Transaction & {
  agent?: TransactionDetail['agent'];
  security_events?: TransactionDetail['security_events'];
};

interface TransactionDetailPanelProps {
  transaction: TransactionWithDetails | null;
  onClose: () => void;
}

export function TransactionDetailPanel({ transaction, onClose }: TransactionDetailPanelProps) {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    overview: true,
    risk: true,
    security: true,
    agent: true,
  });

  if (!transaction) return null;

  const riskLevel = transaction.risk_level;
  const riskColors = {
    low: 'bg-success-100 text-success-600 border-success-200',
    medium: 'bg-warning-100 text-warning-600 border-warning-200',
    high: 'bg-orange-100 text-orange-600 border-orange-200',
    critical: 'bg-danger-100 text-danger-600 border-danger-200',
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const renderSection = (title: string, icon: React.ReactNode, sectionKey: string, children: React.ReactNode) => (
    <div className="border border-secondary-200 rounded-xl overflow-hidden">
      <button
        onClick={() => toggleSection(sectionKey)}
        className="w-full px-4 py-3 bg-secondary-50 border-b border-secondary-200 flex items-center justify-between text-left hover:bg-secondary-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center text-primary-600">
            {icon}
          </div>
          <h3 className="font-medium text-secondary-900">{title}</h3>
        </div>
        {expandedSections[sectionKey] ? (
          <ChevronUp className="w-5 h-5 text-secondary-500" />
        ) : (
          <ChevronDown className="w-5 h-5 text-secondary-500" />
        )}
      </button>
      {expandedSections[sectionKey] && (
        <div className="p-4">{children}</div>
      )}
    </div>
  );

  const renderDetailRow = (label: string, value: React.ReactNode) => (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 py-2 border-b border-secondary-100 last:border-0">
      <span className="text-sm text-secondary-500 w-full sm:w-40 flex-shrink-0">{label}</span>
      <span className="text-sm font-medium text-secondary-900 text-right sm:text-left">{value}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-labelledby="detail-title">
      <div className="fixed inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative ml-auto w-full max-w-4xl h-full bg-white flex flex-col shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-secondary-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary-100 flex items-center justify-center">
              <CreditCard className="w-6 h-6 text-primary-600" />
            </div>
            <div>
              <h2 id="detail-title" className="text-lg font-semibold text-secondary-900">Transaction Details</h2>
              <p className="text-sm text-secondary-500">{transaction.transaction_id}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`badge ${getStatusColor(transaction.status)}`}>
              {transaction.status.replace('_', ' ')}
            </span>
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-secondary-500 hover:bg-secondary-100 hover:text-secondary-700 transition-colors"
              aria-label="Close panel"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Risk Score Banner */}
          <div className={`p-4 rounded-xl border ${riskColors[riskLevel as keyof typeof riskColors]}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-xl bg-white/50 flex items-center justify-center">
                  <span className="text-2xl font-bold text-secondary-900">{transaction.risk_score}</span>
                </div>
                <div>
                  <p className="text-sm text-secondary-500">Risk Score</p>
                  <p className="text-xl font-bold text-secondary-900 capitalize">{riskLevel} Risk</p>
                </div>
              </div>
              {transaction.decision_reason && (
                <div className="text-right max-w-xs">
                  <p className="text-sm text-secondary-500">Decision Reason</p>
                  <p className="text-sm font-medium text-secondary-900">{transaction.decision_reason}</p>
                </div>
              )}
            </div>
          </div>

          {/* Sections */}
          <div className="space-y-4">
            {renderSection('Overview', <DollarSign className="w-5 h-5" />, 'overview', (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {renderDetailRow('Amount', <span className="text-xl font-bold">{formatCurrency(transaction.amount_usd)}</span>)}
                {renderDetailRow('Currency', transaction.currency)}
                {renderDetailRow('Merchant', transaction.merchant_name)}
                {renderDetailRow('Category', transaction.merchant_category)}
                {renderDetailRow('Country', (
                  <span className="flex items-center gap-1">
                    <Globe className="w-4 h-4" />
                    <span className="font-mono uppercase">{transaction.merchant_country}</span>
                  </span>
                ))}
                {renderDetailRow('Requested', formatDate(transaction.requested_at))}
                {renderDetailRow('Decided', transaction.decided_at ? formatDate(transaction.decided_at) : '—')}
                {renderDetailRow('Completed', transaction.completed_at ? formatDate(transaction.completed_at) : '—')}
              </div>
            ))}

            {renderSection('Agent', <User className="w-5 h-5" />, 'agent', (
              transaction.agent ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {renderDetailRow('Agent ID', <code className="font-mono">{transaction.agent.agent_id}</code>)}
                  {renderDetailRow('Name', transaction.agent.name)}
                  {renderDetailRow('Status', <span className={`badge ${getStatusColor(transaction.agent.status)}`}>{transaction.agent.status.replace('_', ' ')}</span>)}
                  {renderDetailRow('Owner', `${transaction.agent.owner_name} (${transaction.agent.owner_type})`)}
                  {renderDetailRow('Owner Email', transaction.agent.owner_email)}
                  {renderDetailRow('Daily Limit', formatCurrency(transaction.agent.daily_limit_usd))}
                  {renderDetailRow('Monthly Limit', formatCurrency(transaction.agent.monthly_limit_usd))}
                  {renderDetailRow('Last Active', transaction.agent.last_active_at ? formatDate(transaction.agent.last_active_at) : 'Never')}
                </div>
              ) : (
                <p className="text-secondary-500">Agent information not available</p>
              )
            ))}

            {renderSection('Risk Signals', <Shield className="w-5 h-5" />, 'risk', (
              <div className="space-y-3">
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-sm text-secondary-600">
                    <strong className="text-secondary-900">Risk Level:</strong> {riskLevel.charAt(0).toUpperCase() + riskLevel.slice(1)} ({transaction.risk_score}/100)
                  </p>
                </div>
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-sm text-secondary-600">
                    <strong className="text-secondary-900">Decision:</strong> {transaction.decision_reason || 'No reason provided'}
                  </p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-3 bg-white border border-secondary-200 rounded-lg">
                    <p className="text-xs text-secondary-500">Velocity Check</p>
                    <p className="font-medium text-secondary-900">Normal</p>
                  </div>
                  <div className="p-3 bg-white border border-secondary-200 rounded-lg">
                    <p className="text-xs text-secondary-500">Geographic Check</p>
                    <p className="font-medium text-secondary-900">{transaction.merchant_country === 'US' ? 'Domestic' : 'International'}</p>
                  </div>
                  <div className="p-3 bg-white border border-secondary-200 rounded-lg">
                    <p className="text-xs text-secondary-500">Amount vs. Avg</p>
                    <p className="font-medium text-secondary-900">Within Range</p>
                  </div>
                </div>
                <p className="text-xs text-secondary-500 text-center py-2">
                  ⚠ Risk signals are synthetic demonstration data.
                </p>
              </div>
            ))}

            {renderSection('Security Events', <AlertTriangle className="w-5 h-5" />, 'security', (
              transaction.security_events && transaction.security_events.length > 0 ? (
                <div className="space-y-3">
                  {transaction.security_events.map((event: SecurityEvent) => (
                    <div key={event.id} className="p-3 bg-white border border-secondary-200 rounded-lg">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`badge ${getSeverityColor(event.severity)}`}>{event.severity}</span>
                            <span className="text-sm font-medium text-secondary-900">{event.title}</span>
                          </div>
                          <p className="text-sm text-secondary-600">{event.description}</p>
                          <p className="text-xs text-secondary-400 mt-1">Detected: {formatDate(event.detected_at)}</p>
                        </div>
                        {event.acknowledged_at && (
                          <span className="badge badge-success text-xs">Acknowledged</span>
                        )}
                      </div>
                      {event.details_json && (
                        <details className="mt-2">
                          <summary className="text-xs text-secondary-500 cursor-pointer">View details</summary>
                          <pre className="mt-2 p-2 bg-secondary-50 rounded text-xs overflow-x-auto">
                            {JSON.stringify(parseJsonSafe(event.details_json, {}), null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <Shield className="w-12 h-12 text-secondary-300 mx-auto mb-2" />
                  <p className="text-secondary-500">No security events recorded for this transaction</p>
                </div>
              )
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
