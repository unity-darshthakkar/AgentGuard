/** AG Grid component for authorization decisions table */

import { AgGridReact } from 'ag-grid-react';
import { ColDef, GridReadyEvent, RowClickedEvent, SelectionChangedEvent } from 'ag-grid-community';
import { useMemo } from 'react';
import type { AuthorizationDecisionRecord, AuthorizationDecision } from '../../types';
import { formatCurrency, formatDate } from '../../utils/formatters';

interface AuthorizationDecisionGridProps {
  rowData: AuthorizationDecisionRecord[];
  onRowClick?: (decision: AuthorizationDecisionRecord) => void;
  onSelectionChange?: (selectedDecisions: AuthorizationDecisionRecord[]) => void;
}

export function AuthorizationDecisionGrid({
  rowData,
  onRowClick,
  onSelectionChange,
}: AuthorizationDecisionGridProps) {
  const columnDefs = useMemo<ColDef<AuthorizationDecisionRecord>[]>(() => [
    {
      headerName: '',
      width: 50,
      pinned: 'left',
      suppressHeaderMenuButton: true,
    },
    {
      headerName: 'Decision Timestamp',
      field: 'decided_at',
      minWidth: 180,
      pinned: 'left',
      valueFormatter: (params: any) => formatDate(params.value),
      cellStyle: { fontWeight: 500, fontFamily: 'monospace', textAlign: 'left' },
    },
    {
      headerName: 'Agent ID',
      field: 'agent_id',
      minWidth: 130,
      valueFormatter: (params: any) => `AGT-${params.value.toString().padStart(3, '0')}`,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'monospace' },
    },
    {
      headerName: 'Request ID',
      field: 'request_id',
      minWidth: 160,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'monospace' },
    },
    {
      headerName: 'Merchant ID',
      field: 'merchant_id',
      minWidth: 150,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'monospace' },
    },
    {
      headerName: 'Amount',
      field: 'amount_cents',
      minWidth: 130,
      valueFormatter: (params: any) => formatCurrency(params.value / 100, params.data?.currency || 'USD'),
      cellStyle: { textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' },
    },
    {
      headerName: 'Currency',
      field: 'currency',
      minWidth: 90,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Decision',
      field: 'decision',
      minWidth: 120,
      cellRenderer: (params: { value: AuthorizationDecision }) => {
        const decision = params.value;
        const decisionColors: Record<AuthorizationDecision, string> = {
          allow: 'bg-success-100 text-success-700 border-success-200',
          block: 'bg-danger-100 text-danger-700 border-danger-200',
          review: 'bg-warning-100 text-warning-700 border-warning-200',
        };
        return (
          <span
            className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${decisionColors[decision] || 'bg-secondary-100 text-secondary-700 border-secondary-200'}`}
          >
            {decision.toUpperCase()}
          </span>
        );
      },
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Policy Violations',
      field: 'policy_violations',
      minWidth: 160,
      flex: 1,
      cellRenderer: (params: any) => {
        const violations = params.value;
        if (!violations || violations.length === 0) {
          return <span className="text-secondary-400 font-mono">—</span>;
        }
        return (
          <div className="flex flex-wrap gap-1">
            {violations.map((v: string, i: number) => (
              <span
                key={i}
                className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono bg-secondary-100 text-secondary-700 border border-secondary-200"
              >
                {v}
              </span>
            ))}
          </div>
        );
      },
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Reasons',
      field: 'reasons',
      minWidth: 150,
      cellRenderer: (params: any) => {
        const reasons = params.value;
        if (!reasons || reasons.length === 0) {
          return <span className="text-secondary-400">—</span>;
        }
        return (
          <span className="text-sm text-secondary-600 max-w-xs truncate block" title={reasons.join(', ')}>
            {reasons.join(', ')}
          </span>
        );
      },
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Idempotency Key',
      field: 'idempotency_key',
      minWidth: 140,
      cellRenderer: (params: any) => params.value ? (
        <code className="text-xs bg-secondary-100 px-1.5 py-0.5 rounded font-mono">{params.value}</code>
      ) : (
        <span className="text-secondary-400">—</span>
      ),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Credential ID',
      field: 'credential_id',
      minWidth: 110,
      cellRenderer: (params: any) => params.value ? (
        <span className="font-mono text-sm">{params.value}</span>
      ) : (
        <span className="text-secondary-400">—</span>
      ),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Policy ID',
      field: 'policy_id',
      minWidth: 100,
      cellRenderer: (params: any) => params.value ? (
        <span className="font-mono text-sm">{params.value}</span>
      ) : (
        <span className="text-secondary-400">—</span>
      ),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
  ], []);

  const defaultColDef = useMemo<ColDef>(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    minWidth: 100,
  }), []);

  const onGridReady = (params: GridReadyEvent<AuthorizationDecisionRecord>) => {
    params.api.sizeColumnsToFit();
  };

  const handleRowClicked = (event: RowClickedEvent<AuthorizationDecisionRecord>) => {
    if (event.data && onRowClick) {
      onRowClick(event.data);
    }
  };

  const handleSelectionChanged = (event: SelectionChangedEvent) => {
    const api = event.api;
    const selected = api.getSelectedRows();
    if (onSelectionChange) {
      onSelectionChange(selected);
    }
  };

  return (
    <div className="h-full w-full" style={{ height: 600 }}>
      <AgGridReact<AuthorizationDecisionRecord>
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        onGridReady={onGridReady}
        onRowClicked={handleRowClicked}
        onSelectionChanged={handleSelectionChanged}
        rowSelection={{ mode: 'multiRow', checkboxes: true, headerCheckbox: true }}
        pagination={true}
        paginationPageSize={20}
        paginationPageSizeSelector={[10, 20, 50, 100]}
        animateRows={true}
        className="ag-theme-quartz"
        rowHeight={48}
        headerHeight={44}
        suppressRowHoverHighlight={false}
      />
    </div>
  );
}