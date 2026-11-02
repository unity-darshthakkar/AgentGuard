/** Transactions monitoring page */

import { useState, useMemo } from 'react';
import { Filter, Download, Search, X } from 'lucide-react';
import { useTransactions } from '../hooks/useApi';
import { TransactionGrid } from '../components/grid/TransactionGrid';
import { TransactionDetailPanel } from '../components/panels/TransactionDetailPanel';
import { LoadingState, ErrorState, EmptyState } from '../components/ui/States';
import { downloadCsv } from '../utils/csv';

const statusOptions: { value: string; label: string }[] = [
  { value: '', label: 'All Statuses' },
  { value: 'approved', label: 'Approved' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'under_review', label: 'Under Review' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
];

const riskOptions: { value: string; label: string }[] = [
  { value: '', label: 'All Risk Levels' },
  { value: 'low', label: 'Low (0-30)' },
  { value: 'medium', label: 'Medium (31-69)' },
  { value: 'high', label: 'High (70-89)' },
  { value: 'critical', label: 'Critical (90-100)' },
];

export function Transactions() {
  const [statusFilter, setStatusFilter] = useState('');
  const [riskFilter, setRiskFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTransaction, setSelectedTransaction] = useState<number | null>(null);

  const { data, loading, error, refetch, pagination, setPagination, totalPages } = useTransactions({
    status: statusFilter || undefined,
    min_risk: riskFilter === 'low' ? 0 : riskFilter === 'medium' ? 31 : riskFilter === 'high' ? 70 : riskFilter === 'critical' ? 90 : undefined,
    max_risk: riskFilter === 'low' ? 30 : riskFilter === 'medium' ? 69 : riskFilter === 'high' ? 89 : riskFilter === 'critical' ? 100 : undefined,
  });

  // Local search filtering on current page data
  const filteredItems = useMemo(() => {
    if (!data?.items || !searchQuery.trim()) return data?.items || [];
    const query = searchQuery.toLowerCase();
    return data.items.filter(txn =>
      txn.transaction_id.toLowerCase().includes(query) ||
      txn.merchant_name.toLowerCase().includes(query) ||
      txn.merchant_category.toLowerCase().includes(query) ||
      txn.description?.toLowerCase().includes(query) ||
      txn.merchant_country.toLowerCase().includes(query)
    );
  }, [data?.items, searchQuery]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPagination({ page: 1 });
  };

  const handleRiskChange = (value: string) => {
    setRiskFilter(value);
    setPagination({ page: 1 });
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setPagination({ page: 1 });
  };

  const handleRowClick = (txn: any) => {
    setSelectedTransaction(txn.id);
  };

  const closeDetailPanel = () => {
    setSelectedTransaction(null);
  };

  const clearSearch = () => {
    setSearchQuery('');
    setPagination({ page: 1 });
  };

  if (loading && !data) {
    return <LoadingState message="Loading transactions..." />;
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
              placeholder="Search transactions (merchant, ID, category)..."
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
              value={statusFilter}
              onChange={(e) => handleStatusChange(e.target.value)}
              className="input pl-10 pr-8 w-40"
            >
              {statusOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="relative">
            <select
              value={riskFilter}
              onChange={(e) => handleRiskChange(e.target.value)}
              className="input pr-8 w-44"
            >
              {riskOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="flex-1" />
          <span className="text-sm text-secondary-500">
            {filteredItems.length} of {data?.total || 0} transactions
          </span>
          <button className="btn-secondary" onClick={() => downloadCsv('agentguard-transactions-page.csv', filteredItems, [{ key: 'transaction_id', label: 'Transaction ID' }, { key: 'merchant_name', label: 'Merchant' }, { key: 'amount_usd', label: 'Amount USD' }, { key: 'currency', label: 'Currency' }, { key: 'status', label: 'Status' }, { key: 'risk_score', label: 'Risk Score' }])} title="Exports the current filtered page">
            <Download className="w-4 h-4" />
            Export current page
          </button>
        </div>

        {/* Grid */}
        {filteredItems && filteredItems.length > 0 ? (
          <TransactionGrid
            rowData={filteredItems}
            onRowClick={handleRowClick}
          />
        ) : (
          <EmptyState
            title="No transactions found"
            message={searchQuery ? `No transactions match "${searchQuery}"` : "No transactions match the current filters"}
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

      {/* Transaction Detail Panel */}
      {selectedTransaction && (
        <TransactionDetailPanel
          transaction={data?.items.find(t => t.id === selectedTransaction) || null}
          onClose={closeDetailPanel}
        />
      )}

      {/* Demo Notice - compact */}
      <div className="mt-4 p-3 bg-primary-50 border border-primary-200 rounded-lg">
        <p className="text-xs text-primary-700">
          Transaction data is synthetic demonstration data. Export includes the current filtered page.
        </p>
      </div>
    </>
  );
}
