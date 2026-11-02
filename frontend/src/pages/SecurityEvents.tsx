/** Security Events page */

import { useState, useMemo } from 'react';
import { Filter, Download, AlertTriangle, Shield, Bell, Clock, ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import { EmptyState, LoadingState, ErrorState } from '../components/ui/States';
import { SecurityEvent, SecurityEventSeverity, SecurityEventType } from '../types';
import { formatDate, getSeverityColor, parseJsonSafe } from '../utils/formatters';
import { useSecurityEvents } from '../hooks/useApi';
import { downloadCsv } from '../utils/csv';

const severityOptions: { value: string; label: string }[] = [
  { value: '', label: 'All Severities' },
  { value: 'info', label: 'Info' },
  { value: 'warning', label: 'Warning' },
  { value: 'critical', label: 'Critical' },
];

const typeOptions: { value: string; label: string }[] = [
  { value: '', label: 'All Types' },
  { value: 'velocity_anomaly', label: 'Velocity Anomaly' },
  { value: 'geo_anomaly', label: 'Geographic Anomaly' },
  { value: 'amount_outlier', label: 'Amount Outlier' },
  { value: 'new_merchant', label: 'New Merchant' },
  { value: 'permission_violation', label: 'Permission Violation' },
  { value: 'pattern_deviation', label: 'Pattern Deviation' },
];

const acknowledgedOptions: { value: string; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'unacknowledged', label: 'Unacknowledged' },
];

export function SecurityEvents() {
  const [severityFilter, setSeverityFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [acknowledgedFilter, setAcknowledgedFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEvent, setSelectedEvent] = useState<SecurityEvent | null>(null);

  const { data, loading, error, refetch, pagination, setPagination, totalPages } = useSecurityEvents({
    severity: severityFilter || undefined,
    event_type: typeFilter || undefined,
    // Note: acknowledged filter is not supported by API yet, will do client-side filtering
  });

  // Client-side filtering for acknowledged status + local search
  const filteredEvents = useMemo(() => {
    let events = data?.items.filter(event => {
      if (acknowledgedFilter === 'acknowledged' && !event.acknowledged_at) return false;
      if (acknowledgedFilter === 'unacknowledged' && event.acknowledged_at) return false;
      return true;
    }) || [];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      events = events.filter(event =>
        event.event_id.toLowerCase().includes(query) ||
        event.title.toLowerCase().includes(query) ||
        (event.description || '').toLowerCase().includes(query) ||
        event.event_type.toLowerCase().includes(query) ||
        event.severity.toLowerCase().includes(query) ||
        `agent #${event.agent_id}`.toLowerCase().includes(query)
      );
    }
    return events;
  }, [data?.items, searchQuery, acknowledgedFilter]);

  const clearSearch = () => {
    setSearchQuery('');
    setPagination({ page: 1 });
  };

  const handleStatusChange = (value: string) => {
    setSeverityFilter(value);
    setPagination({ page: 1 });
  };

  const handleTypeChange = (value: string) => {
    setTypeFilter(value);
    setPagination({ page: 1 });
  };

  const handleAcknowledgedChange = (value: string) => {
    setAcknowledgedFilter(value);
    setPagination({ page: 1 });
  };

  const getSeverityIcon = (severity: SecurityEventSeverity) => {
    switch (severity) {
      case 'critical':
        return <AlertTriangle className="w-4 h-4 text-danger-600" />;
      case 'warning':
        return <Bell className="w-4 h-4 text-warning-600" />;
      case 'info':
        return <Shield className="w-4 h-4 text-primary-600" />;
    }
  };

  const formatEventType = (type: SecurityEventType) => {
    return type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  if (loading && !data) {
    return <LoadingState message="Loading security events..." />;
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
              placeholder="Search events (title, ID, type, agent)..."
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
              value={severityFilter}
              onChange={(e) => handleStatusChange(e.target.value)}
              className="input pl-10 pr-8 w-40"
            >
              {severityOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <select
            value={typeFilter}
            onChange={(e) => handleTypeChange(e.target.value)}
            className="input w-48"
          >
            {typeOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <select
            value={acknowledgedFilter}
            onChange={(e) => handleAcknowledgedChange(e.target.value)}
            className="input w-40"
          >
            {acknowledgedOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <div className="flex-1" />
          <span className="text-sm text-secondary-500">
            {filteredEvents.length} of {data?.total || 0} events
          </span>
          <button className="btn-secondary" onClick={() => downloadCsv('agentguard-security-events-page.csv', filteredEvents, [{ key: 'event_id', label: 'Event ID' }, { key: 'event_type', label: 'Type' }, { key: 'severity', label: 'Severity' }, { key: 'title', label: 'Title' }, { key: 'agent_id', label: 'Agent ID' }, { key: 'detected_at', label: 'Detected At' }])} title="Exports the current filtered page">
            <Download className="w-4 h-4" />
            Export current page
          </button>
        </div>

        {/* Events Table */}
        {filteredEvents.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-secondary-50 border-b border-secondary-200">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Severity</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Title</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Agent</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Detected</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-secondary-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-secondary-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {filteredEvents.map(event => (
                  <tr key={event.id} className="hover:bg-secondary-50 cursor-pointer" onClick={() => setSelectedEvent(event)}>
                    <td className="px-4 py-3">
                      <span className={`badge ${getSeverityColor(event.severity)} flex items-center gap-1`}>
                        {getSeverityIcon(event.severity)}
                        {event.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-secondary-600">{formatEventType(event.event_type)}</td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-secondary-900">{event.title}</p>
                      <p className="text-sm text-secondary-500 truncate max-w-xs">{event.description}</p>
                    </td>
                    <td className="px-4 py-3 text-sm text-secondary-600">Agent #{event.agent_id}</td>
                    <td className="px-4 py-3 text-sm text-secondary-600 whitespace-nowrap">
                      <Clock className="w-3.5 h-3.5 inline mr-1" />
                      {formatDate(event.detected_at)}
                    </td>
                    <td className="px-4 py-3">
                      {event.acknowledged_at ? (
                        <span className="badge badge-success">Acknowledged</span>
                      ) : (
                        <span className="badge badge-warning">Pending</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={(e) => { e.stopPropagation(); setSelectedEvent(event); }}
                        className="btn-secondary text-sm"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No security events found"
            message={searchQuery ? `No events match "${searchQuery}"` : "No events match the current filters"}
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
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                className="btn-secondary"
                onClick={() => setPagination({ page: pagination.page + 1 })}
                disabled={pagination.page >= totalPages}
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Event Detail Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true">
          <div className="fixed inset-0 bg-black/50" onClick={() => setSelectedEvent(null)} />
          <div className="relative ml-auto w-full max-w-3xl h-full bg-white flex flex-col shadow-xl">
            <div className="flex items-center justify-between p-4 border-b border-secondary-200">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl ${getSeverityColor(selectedEvent.severity).replace('text-', 'bg-').replace('600', '100')} flex items-center justify-center`}>
                  {getSeverityIcon(selectedEvent.severity)}
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-secondary-900">{selectedEvent.title}</h2>
                  <p className="text-sm text-secondary-500">{selectedEvent.event_id}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedEvent(null)}
                className="p-2 rounded-lg text-secondary-500 hover:bg-secondary-100"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-xs text-secondary-500">Severity</p>
                  <p className="font-medium text-secondary-900 capitalize">{selectedEvent.severity}</p>
                </div>
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-xs text-secondary-500">Type</p>
                  <p className="font-medium text-secondary-900">{formatEventType(selectedEvent.event_type)}</p>
                </div>
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-xs text-secondary-500">Agent</p>
                  <p className="font-medium text-secondary-900">Agent #{selectedEvent.agent_id}</p>
                </div>
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-xs text-secondary-500">Transaction</p>
                  <p className="font-medium text-secondary-900">{selectedEvent.transaction_id ? `#${selectedEvent.transaction_id}` : 'N/A'}</p>
                </div>
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-xs text-secondary-500">Detected</p>
                  <p className="font-medium text-secondary-900">{formatDate(selectedEvent.detected_at)}</p>
                </div>
                <div className="p-3 bg-secondary-50 rounded-lg">
                  <p className="text-xs text-secondary-500">Status</p>
                  <p className="font-medium text-secondary-900">
                    {selectedEvent.acknowledged_at ? 'Acknowledged' : 'Unacknowledged'}
                  </p>
                </div>
              </div>

              <div className="p-4 bg-white border border-secondary-200 rounded-lg">
                <h3 className="font-medium text-secondary-900 mb-2">Description</h3>
                <p className="text-secondary-600">{selectedEvent.description}</p>
              </div>

              {selectedEvent.details_json && (
                <details className="p-4 bg-white border border-secondary-200 rounded-lg">
                  <summary className="font-medium text-secondary-900 cursor-pointer">Event Details (JSON)</summary>
                  <pre className="mt-2 p-3 bg-secondary-50 rounded text-xs overflow-x-auto font-mono">
                    {JSON.stringify(parseJsonSafe(selectedEvent.details_json, {}), null, 2)}
                  </pre>
                </details>
              )}

              {selectedEvent.acknowledged_at && (
                <div className="p-4 bg-success-50 border border-success-200 rounded-lg">
                  <p className="text-sm text-success-700">
                    <strong>Acknowledged by:</strong> {selectedEvent.acknowledged_by} at {formatDate(selectedEvent.acknowledged_at)}
                  </p>
                </div>
              )}

              {!selectedEvent.acknowledged_at && (
                <div className="pt-4 border-t border-secondary-200">
                  <button className="btn-primary w-full" disabled>
                    <Bell className="w-4 h-4" />
                    Acknowledge Event (Not available)
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Demo Notice - compact */}
      <div className="mt-4 p-3 bg-primary-50 border border-primary-200 rounded-lg">
        <p className="text-xs text-primary-700">
          Security events are synthetic demonstration data. Acknowledge is unavailable in this read-only dashboard.
        </p>
      </div>
    </>
  );
}
