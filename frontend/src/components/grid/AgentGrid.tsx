/** AG Grid component for agents table */

import { AgGridReact } from 'ag-grid-react';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import { ColDef, GridReadyEvent, RowClickedEvent, SelectionChangedEvent } from 'ag-grid-community';
import { useMemo } from 'react';
import type { Agent, AgentStatus } from '../../types';
import { getStatusColor, formatCurrency, formatDate } from '../../utils/formatters';

interface AgentGridProps {
  rowData: Agent[];
  onRowClick?: (agent: Agent) => void;
  onSelectionChange?: (selectedAgents: Agent[]) => void;
}

export function AgentGrid({ rowData, onRowClick, onSelectionChange }: AgentGridProps) {
  const columnDefs = useMemo<ColDef<Agent>[]>(() => [
    {
      headerName: '',
      width: 50,
      pinned: 'left',
      suppressHeaderMenuButton: true,
    },
    {
      headerName: 'Agent ID',
      field: 'agent_id',
      minWidth: 140,
      pinned: 'left',
      cellStyle: { fontWeight: 500, fontFamily: 'monospace', textAlign: 'left' },
    },
    {
      headerName: 'Name',
      field: 'name',
      minWidth: 180,
      flex: 1,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Status',
      field: 'status',
      minWidth: 130,
      cellRenderer: (params: { value: AgentStatus }) => (
        <span className={`badge ${getStatusColor(params.value)}`}>
          {params.value.replace('_', ' ')}
        </span>
      ),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Owner',
      field: 'owner_name',
      minWidth: 150,
      valueGetter: (params: any) => params.data ? `${params.data.owner_name} (${params.data.owner_type})` : '',
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Owner Email',
      field: 'owner_email',
      minWidth: 200,
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Daily Limit',
      field: 'daily_limit_usd',
      minWidth: 130,
      valueFormatter: (params: any) => formatCurrency(params.value),
      cellStyle: { textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' },
    },
    {
      headerName: 'Monthly Limit',
      field: 'monthly_limit_usd',
      minWidth: 140,
      valueFormatter: (params: any) => formatCurrency(params.value),
      cellStyle: { textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' },
    },
    {
      headerName: 'Last Active',
      field: 'last_active_at',
      minWidth: 160,
      valueFormatter: (params: any) => params.value ? formatDate(params.value) : 'Never',
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
    {
      headerName: 'Created',
      field: 'created_at',
      minWidth: 140,
      valueFormatter: (params: any) => formatDate(params.value),
      cellStyle: { textAlign: 'left', fontWeight: 400, fontFamily: 'inherit' },
    },
  ], []);

  const defaultColDef = useMemo<ColDef>(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    minWidth: 100,
  }), []);

  const onGridReady = (params: GridReadyEvent<Agent>) => {
    params.api.sizeColumnsToFit();
  };

  const handleRowClicked = (event: RowClickedEvent<Agent>) => {
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
      <AgGridReact<Agent>
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