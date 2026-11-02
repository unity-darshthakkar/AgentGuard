/** Authorization Decision Detail Panel */

import { X, ChevronDown, ChevronUp, AlertTriangle, Shield, DollarSign, FileText, Key } from 'lucide-react';
import { useState } from 'react';
import type { AuthorizationDecisionRecord, AuthorizationDecision } from '../../types';
import { formatCurrency, formatDate } from '../../utils/formatters';

interface AuthorizationDecisionDetailPanelProps {
  decision: AuthorizationDecisionRecord | null;
  onClose: () => void;
}

export function AuthorizationDecisionDetailPanel({ decision, onClose }: AuthorizationDecisionDetailPanelProps) {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    overview: true,
    decision: true,
    budget: true,
    policy: true,
  });

  if (!decision) return null;

  const decisionColors: Record<AuthorizationDecision, string> = {
    allow: 'bg-success-100 text-success-700 border-success-200',
    block: 'bg-danger-100 text-danger-700 border-danger-200',
    review: 'bg-warning-100 text-warning-700 border-warning-200',
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
      <span className="text-sm text-secondary-500 w-full sm:w-48 flex-shrink-0">{label}</span>
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
              <Shield className="w-6 h-6 text-primary-600" />
            </div>
            <div>
              <h2 id="detail-title" className="text-lg font-semibold text-secondary-900">Authorization Decision</h2>
              <p className="text-sm text-secondary-500">{decision.request_id}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${decisionColors[decision.decision] || 'bg-secondary-100 text-secondary-700 border-secondary-200'}`}>
              {decision.decision.toUpperCase()}
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
          {/* Decision Banner */}
          <div className={`p-4 rounded-xl border ${decisionColors[decision.decision]}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-xl bg-white/50 flex items-center justify-center">
                  <span className="text-2xl font-bold text-secondary-900">{decision.decision.toUpperCase()}</span>
                </div>
                <div>
                  <p className="text-sm text-secondary-500">Decision</p>
                  <p className="text-xl font-bold text-secondary-900 capitalize">{decision.decision}</p>
                </div>
              </div>
              <div className="text-right max-w-xs">
                <p className="text-sm text-secondary-500">Timestamp</p>
                <p className="text-sm font-medium text-secondary-900">{formatDate(decision.decided_at)}</p>
              </div>
            </div>
          </div>

          {/* Sections */}
          <div className="space-y-4">
            {renderSection('Transaction Details', <DollarSign className="w-5 h-5" />, 'overview', (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {renderDetailRow('Amount', <span className="text-xl font-bold">{formatCurrency(decision.amount_cents / 100, decision.currency)}</span>)}
                {renderDetailRow('Currency', decision.currency)}
                {renderDetailRow('Merchant ID', <code className="font-mono">{decision.merchant_id}</code>)}
                {renderDetailRow('Merchant Category', decision.merchant_category)}
                {renderDetailRow('Request ID', <code className="font-mono">{decision.request_id}</code>)}
                {renderDetailRow('Idempotency Key', decision.idempotency_key ? <code className="font-mono text-xs">{decision.idempotency_key}</code> : '—')}
                {renderDetailRow('Decided At', formatDate(decision.decided_at))}
                {renderDetailRow('Description', decision.description || '—')}
              </div>
            ))}

            {renderSection('Decision Reasons', <FileText className="w-5 h-5" />, 'decision', (
              <div className="space-y-3">
                {decision.reasons && decision.reasons.length > 0 ? (
                  <div className="space-y-2">
                    {decision.reasons.map((reason, i) => (
                      <div key={i} className="p-3 bg-secondary-50 rounded-lg border border-secondary-200">
                        <p className="text-sm text-secondary-900">{reason}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-secondary-500">No reasons provided for this decision</p>
                )}

                {decision.policy_violations && decision.policy_violations.length > 0 && (
                  <div className="pt-2 border-t border-secondary-200">
                    <p className="text-sm font-medium text-secondary-900 mb-2">Policy Violations</p>
                    <div className="flex flex-wrap gap-2">
                      {decision.policy_violations.map((violation, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center px-2.5 py-1 rounded text-xs font-medium bg-danger-50 text-danger-700 border border-danger-200"
                        >
                          <AlertTriangle className="w-3 h-3 mr-1" />
                          {violation}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {renderSection('Budget Impact', <Shield className="w-5 h-5" />, 'budget', (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {renderDetailRow('Daily Spent Before', <span className="font-mono text-lg">{formatCurrency(decision.daily_spent_before_cents / 100, decision.currency)}</span>)}
                {renderDetailRow('Transaction Amount', <span className="font-mono text-lg text-primary-600">{formatCurrency(decision.amount_cents / 100, decision.currency)}</span>)}
                {renderDetailRow('Daily Spent After', <span className="font-mono text-lg font-bold">{formatCurrency(decision.daily_spent_after_cents / 100, decision.currency)}</span>)}
                {renderDetailRow('Budget Remaining', <span className="font-mono text-lg">{formatCurrency(Math.max(0, (decision.daily_spent_after_cents - decision.daily_spent_before_cents)) / 100, decision.currency)}</span>)}
              </div>
            ))}

            {renderSection('Policy & Credentials', <Key className="w-5 h-5" />, 'policy', (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {renderDetailRow('Agent ID', <code className="font-mono">AGT-{decision.agent_id.toString().padStart(3, '0')}</code>)}
                {renderDetailRow('Credential ID', decision.credential_id ? <code className="font-mono">{decision.credential_id}</code> : <span className="text-secondary-400">—</span>)}
                {renderDetailRow('Policy ID', decision.policy_id ? <code className="font-mono">{decision.policy_id}</code> : <span className="text-secondary-400">—</span>)}
                {renderDetailRow('Internal Decision ID', <code className="font-mono">{decision.id}</code>)}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}