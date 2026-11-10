/** Loading, Error, and Empty state components */

import { RefreshCw, AlertCircle, Inbox, Database } from 'lucide-react';
import { useEffect, useState } from 'react';

export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  const [waking, setWaking] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setWaking(true), 5_000);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="relative w-10 h-10 mb-4">
        <svg className="animate-spin w-full h-full text-primary-600" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      </div>
      <p className="text-secondary-500">{waking ? "Our demo server is waking up. This can take about a minute on free hosting." : message}</p>
    </div>
  );
}

export function ErrorState({
  message = 'Something went wrong',
  onRetry,
}: { message?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-16 h-16 rounded-full bg-danger-100 flex items-center justify-center mb-4">
        <AlertCircle className="w-8 h-8 text-danger-600" />
      </div>
      <h3 className="text-lg font-medium text-secondary-900 mb-1">Unable to load data</h3>
      <p className="text-secondary-500 mb-4 max-w-md">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn-primary flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Try Again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title = 'No data found',
  message = 'Get started by creating a new item',
  action,
}: { title?: string; message?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-16 h-16 rounded-full bg-secondary-100 flex items-center justify-center mb-4">
        <Inbox className="w-8 h-8 text-secondary-400" />
      </div>
      <h3 className="text-lg font-medium text-secondary-900 mb-1">{title}</h3>
      <p className="text-secondary-500 mb-4 max-w-md">{message}</p>
      {action && <div>{action}</div>}
    </div>
  );
}

export function TableLoadingState({ rows = 5 }: { rows?: number }) {
  const [waking, setWaking] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setWaking(true), 5_000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="space-y-3">
      {waking && (
        <p className="text-sm text-slate-500" role="status" aria-live="polite">
          Our demo server is waking up. This can take about a minute on free hosting.
        </p>
      )}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="animate-pulse">
          <div className="h-12 bg-secondary-100 rounded-lg" />
        </div>
      ))}
    </div>
  );
}

export function TableErrorState({
  message = 'Failed to load data',
  onRetry,
}: { message?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-16 h-16 rounded-full bg-danger-100 flex items-center justify-center mb-4">
        <Database className="w-8 h-8 text-danger-600" />
      </div>
      <h3 className="text-lg font-medium text-secondary-900 mb-1">Unable to load table data</h3>
      <p className="text-secondary-500 mb-4 max-w-md">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn-primary flex items-center gap-2">
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      )}
    </div>
  );
}
