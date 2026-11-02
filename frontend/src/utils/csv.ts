export function downloadCsv<T>(filename: string, rows: T[], columns: { key: keyof T; label: string }[]) {
  const escape = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const content = [columns.map(column => escape(column.label)).join(','), ...rows.map(row => columns.map(column => escape(row[column.key])).join(','))].join('\r\n');
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  URL.revokeObjectURL(url);
}
