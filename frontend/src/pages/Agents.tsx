/** Agents registry page */

import { useState, useMemo } from 'react';
import { Plus, Filter, Download, Search, X } from 'lucide-react';
import { useAgents } from '../hooks/useApi';
import { AgentGrid } from '../components/grid/AgentGrid';
import { LoadingState, ErrorState, EmptyState } from '../components/ui/States';
import { downloadCsv } from '../utils/csv';

const statusOptions: { value: string; label: string }[] = [
  { value: '', label: 'All Statuses' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'pending_review', label: 'Pending Review' },
  { value: 'decommissioned', label: 'Decommissioned' },
];

export function Agents() {
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const { data, loading, error, refetch, pagination, setPagination, totalPages } = useAgents({
    status: statusFilter || undefined,
  });

  // Local search filtering on current page data
  const filteredItems = useMemo(() => {
    if (!data?.items || !searchQuery.trim()) return data?.items || [];
    const query = searchQuery.toLowerCase();
    return data.items.filter(agent =>
      agent.agent_id.toLowerCase().includes(query) ||
      agent.name.toLowerCase().includes(query) ||
      agent.owner_name.toLowerCase().includes(query) ||
      agent.owner_email.toLowerCase().includes(query) ||
      agent.owner_type.toLowerCase().includes(query) ||
      agent.status.toLowerCase().includes(query)
    );
  }, [data?.items, searchQuery]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPagination({ page: 1 });
  };

  const clearSearch = () => {
    setSearchQuery('');
    setPagination({ page: 1 });
  };

  if (loading && !data) {
    return <LoadingState message="Loading agents..." />;
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
              placeholder="Search agents (ID, name, owner, email)..."
              className="input pl-10 pr-10"
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setPagination({ page: 1 }); }}
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
              value={statusFilter}
              onChange={(e) => handleStatusChange(e.target.value)}
              className="input pl-10 pr-8 w-48"
            >
              {statusOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="flex-1" />
          <span className="text-sm text-secondary-500">
            {filteredItems.length} of {data?.total || 0} agents
          </span>
          <button className="btn-secondary" onClick={() => downloadCsv('agentguard-agents.csv', filteredItems, [{ key: 'agent_id', label: 'Agent ID' }, { key: 'name', label: 'Name' }, { key: 'status', label: 'Status' }, { key: 'owner_name', label: 'Owner' }, { key: 'owner_email', label: 'Owner Email' }])}>
            <Download className="w-4 h-4" />
            Export current page
          </button>
        </div>

        {filteredItems && filteredItems.length > 0 ? (
          <AgentGrid
            rowData={filteredItems}
            onRowClick={(agent) => {
              // Navigate to agent detail - for now just log
              console.log('Agent clicked:', agent);
            }}
          />
        ) : (
          <EmptyState
            title="No agents found"
            message={searchQuery ? `No agents match "${searchQuery}"` : (statusFilter ? `No agents with status "${statusOptions.find(o => o.value === statusFilter)?.label}"` : 'No agents have been registered yet')}
            action={
              <button className="btn-primary" disabled>
                <Plus className="w-4 h-4" />
                Add Agent
              </button>
            }
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

      {/* Demo Notice - compact */}
      <div className="mt-4 p-3 bg-primary-50 border border-primary-200 rounded-lg">
        <p className="text-xs text-primary-700">
          Agent data is synthetic demonstration data. Spending permissions and identity status are shown from the security API.
        </p>
      </div>
    </>
  );
}
