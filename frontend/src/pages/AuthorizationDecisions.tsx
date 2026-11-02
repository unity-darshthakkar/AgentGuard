/** Authorization Decisions monitoring page */

import { useState, useMemo } from 'react';
import { Filter, Download, Search, X, RefreshCw } from 'lucide-react';
import { useAuthorizationDecisions } from '../hooks/useApi';
import { AuthorizationDecisionGrid } from '../components/grid/AuthorizationDecisionGrid';
import { AuthorizationDecisionDetailPanel } from '../components/panels/AuthorizationDecisionDetailPanel';
import { LoadingState, ErrorState, EmptyState } from '../components/ui/States';
import type { AuthorizationDecision } from '../types';
import { downloadCsv } from '../utils/csv';

const decisionOptions: { value: AuthorizationDecision | ''; label: string }[] = [
  { value: '', label: 'All Decisions' },
  { value: 'allow', label: 'Allowed' },
  { value: 'block', label: 'Blocked' },
  { value: 'review', label: 'Under Review' },
];

export function AuthorizationDecisions() {
  const [decisionFilter, setDecisionFilter] = useState<AuthorizationDecision | ''>('');
  const [agentIdFilter, setAgentIdFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDecision, setSelectedDecision] = useState<number | null>(null);

  const { data, loading, error, refetch, pagination, setPagination, totalPages } = useAuthorizationDecisions({
    decision: decisionFilter || undefined,
    agent_id: agentIdFilter || undefined,
  });

  // Local search filtering on current page data
  const filteredItems = useMemo(() => {
    if (!data?.items || !searchQuery.trim()) return data?.items || [];
    const query = searchQuery.toLowerCase();
    return data.items.filter(decision =>
      decision.request_id.toLowerCase().includes(query) ||
      decision.merchant_id.toLowerCase().includes(query) ||
      decision.merchant_category.toLowerCase().includes(query) ||
      decision.description?.toLowerCase().includes(query) ||
      decision.agent_id.toString().includes(query)
    );
  }, [data?.items, searchQuery]);

  const handleDecisionChange = (value: AuthorizationDecision | '') => {
    setDecisionFilter(value);
    setPagination({ page: 1 });
  };

  const handleAgentIdChange = (value: string) => {
    setAgentIdFilter(value);
    setPagination({ page: 1 });
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setPagination({ page: 1 });
  };

  const handleRowClick = (decision: any) => {
    setSelectedDecision(decision.id);
  };

  const closeDetailPanel = () => {
    setSelectedDecision(null);
  };

  const clearSearch = () => {
    setSearchQuery('');
    setPagination({ page: 1 });
  };

  const clearFilters = () => {
    setDecisionFilter('');
    setAgentIdFilter('');
    setSearchQuery('');
    setPagination({ page: 1 });
  };

  const hasActiveFilters = decisionFilter || agentIdFilter || searchQuery;

  if (loading && !data) {
    return <LoadingState message="Loading authorization decisions..." />;
  }

  if (error && !data) {
    return <ErrorState message={error} onRetry={refetch} />;
  }

  return (
    <>
      <div className="card">
        {/* Filters */}
        <div className="p-4 border-b border-secondary-200 flex flex-wrap items-center gap-4">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary-400" />
            <input
              type="search"
              placeholder="Search decisions (request ID, agent, merchant, category)..."
              className="input pl-10 pr-10"
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-secondary-400 hover:text-secondary-600"
                aria-label="Clear search"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary-400" />
            <select
              value={decisionFilter}
              onChange={(e) => handleDecisionChange(e.target.value as AuthorizationDecision | '')}
              className="input pl-10 pr-8 w-40"
            >
              {decisionOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary-400" />
            <input
              type="text"
              placeholder="Agent ID (e.g., AGT-001)"
              className="input pl-10 pr-8 w-40"
              value={agentIdFilter}
              onChange={(e) => handleAgentIdChange(e.target.value)}
            />
          </div>
          <div className="flex-1" />
          <span className="text-sm text-secondary-500">
            {filteredItems.length} of {data?.total || 0} decisions
          </span>
          {hasActiveFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="btn-secondary text-sm"
            >
              <X className="w-4 h-4 mr-1" />
              Clear Filters
            </button>
          )}
          <button className="btn-secondary" onClick={() => downloadCsv('agentguard-authorization-decisions-page.csv', filteredItems, [{ key: 'request_id', label: 'Request ID' }, { key: 'agent_id', label: 'Agent ID' }, { key: 'decision', label: 'Decision' }, { key: 'amount_cents', label: 'Amount Cents' }, { key: 'currency', label: 'Currency' }, { key: 'merchant_id', label: 'Merchant ID' }])} title="Exports the current filtered page">
            <Download className="w-4 h-4" />
            Export current page
          </button>
          <button
            type="button"
            onClick={refetch}
            className="btn-secondary"
            disabled={loading}
            aria-label="Refresh decisions"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Grid */}
        {filteredItems && filteredItems.length > 0 ? (
          <AuthorizationDecisionGrid
            rowData={filteredItems}
            onRowClick={handleRowClick}
          />
        ) : (
          <EmptyState
            title="No authorization decisions found"
            message={searchQuery || decisionFilter || agentIdFilter
              ? `No decisions match the current filters`
              : "No authorization decisions recorded yet"}
          />
        )}

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="p-4 border-t border-secondary-200 flex items-center justify-between">
            <span className="text-sm text-secondary-500">
              Page {pagination.page} of {totalPages} ({data.total} total)
            </span>
            <div className="flex items-center gap-2">
              <button
                className="btn-secondary"
                onClick={() => setPagination({ page: pagination.page - 1 })}
                disabled={pagination.page <= 1}
              >
                Previous
              </button>
              <button
                className="btn-secondary"
                onClick={() => setPagination({ page: pagination.page + 1 })}
                disabled={pagination.page >= totalPages}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Authorization Decision Detail Panel */}
      {selectedDecision && (
        <AuthorizationDecisionDetailPanel
          decision={data?.items.find(d => d.id === selectedDecision) || null}
          onClose={closeDetailPanel}
        />
      )}

      {/* Demo Notice - compact */}
      <div className="mt-4 p-3 bg-primary-50 border border-primary-200 rounded-lg">
        <p className="text-xs text-primary-700">
          Authorization decision data is synthetic demonstration data from the security API.
        </p>
      </div>
    </>
  );
}
