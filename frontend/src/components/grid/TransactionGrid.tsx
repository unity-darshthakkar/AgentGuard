/** AG Grid component for transactions table */

import { AgGridReact } from 'ag-grid-react';
import { ColDef, GridReadyEvent, RowClickedEvent, SelectionChangedEvent } from 'ag-grid-community';
import { useMemo } from 'react';
import type { Transaction, TransactionStatus } from '../../types';
import { RISK_LEVEL_COLORS } from '../../types';
import { getStatusColor, formatCurrency, formatDate, getRiskLevel } from '../../utils/formatters';

interface TransactionGridProps {
  rowData: Transaction[];
  onRowClick?: (transaction: Transaction) => void;
  onSelectionChange?: (selectedTransactions: Transaction[]) => void;
}

export function TransactionGrid({ rowData, onRowClick, onSelectionChange }: TransactionGridProps) {
  const columnDefs = useMemo<ColDef<Transaction>[]>(() => [
    {
      headerName: '',
      width: 50,
      pinned: 'left',
      suppressHeaderMenuButton: true,
    },
    {
      headerName: 'Transaction ID',
      field: 'transaction_id',
      minWidth: 160,
      pinned: 'left',
      cellStyle: { fontWeight: 500, fontFamily: 'monospace', textAlign: 'left' },
    },
    {
      headerName: 'Agent',
      field: 'agent_id',
      minWidth: 120,
      valueFormatter: (params: any) => `Agent #${params.value}`,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Amount',
      field: 'amount_usd',
      minWidth: 130,
      valueFormatter: (params: any) => formatCurrency(params.value),
      cellStyle: { textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' },
    },
    {
      headerName: 'Merchant',
      field: 'merchant_name',
      minWidth: 180,
      flex: 1,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Category',
      field: 'merchant_category',
      minWidth: 140,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Country',
      field: 'merchant_country',
      minWidth: 100,
      cellRenderer: (params: any) => (
        <span className="font-mono text-sm uppercase">{params.value}</span>
      ),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Status',
      field: 'status',
      minWidth: 130,
      cellRenderer: (params: { value: TransactionStatus }) => (
        <span className={`badge ${getStatusColor(params.value)}`}>
          {params.value.replace('_', ' ')}
        </span>
      ),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Risk Score',
      field: 'risk_score',
      minWidth: 120,
      cellRenderer: (params: any) => {
        const score = params.value;
        const level = getRiskLevel(score);
        return (
          <div className="flex items-center gap-2">
            <div className="w-24 h-2 bg-secondary-200 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${score}%`,
                  backgroundColor:
                    level === 'low' ? '#22c55e' :
                    level === 'medium' ? '#f59e0b' :
                    level === 'high' ? '#f97316' :
                    '#ef4444',
                }}
              />
            </div>
            <span className={`text-sm font-mono ${RISK_LEVEL_COLORS[level]}`}>
              {score}
            </span>
          </div>
        );
      },
    },
    {
      headerName: 'Risk Level',
      field: 'risk_level',
      minWidth: 110,
      cellRenderer: (params: any) => (
        <span className={`badge ${RISK_LEVEL_COLORS[params.value as keyof typeof RISK_LEVEL_COLORS] || 'badge-neutral'}`}>
          {params.value}
        </span>
      ),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Requested',
      field: 'requested_at',
      minWidth: 160,
      valueFormatter: (params: any) => formatDate(params.value),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Decided',
      field: 'decided_at',
      minWidth: 160,
      valueFormatter: (params: any) => params.value ? formatDate(params.value) : '—',
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
  ], []);

  const defaultColDef = useMemo<ColDef>(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    minWidth: 100,
  }), []);

  const onGridReady = (params: GridReadyEvent<Transaction>) => {
    params.api.sizeColumnsToFit();
  };

  const handleRowClicked = (event: RowClickedEvent<Transaction>) => {
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
      <AgGridReact<Transaction>
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