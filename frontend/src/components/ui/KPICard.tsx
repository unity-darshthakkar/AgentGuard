/** KPI Card component for dashboard metrics */

import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: { value: number; label: string };
  icon?: React.ReactNode;
  iconBg?: string;
  iconColor?: string;
}

export function KPICard({ title, value, subtitle, trend, icon, iconBg = 'bg-primary-100', iconColor = 'text-primary-600' }: KPICardProps) {
  const trendIcon = trend
    ? trend.value > 0
      ? <TrendingUp className="w-4 h-4 text-success-600" />
      : trend.value < 0
      ? <TrendingDown className="w-4 h-4 text-danger-600" />
      : <Minus className="w-4 h-4 text-secondary-400" />
    : null;

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-secondary-500">{title}</p>
          <p className="mt-1 text-3xl font-bold text-secondary-900">{value}</p>
          {subtitle && (
            <p className="mt-1 text-sm text-secondary-500">{subtitle}</p>
          )}
        </div>
        {icon && (
          <div className={`${iconBg} ${iconColor} p-3 rounded-xl`}>
            {icon}
          </div>
        )}
      </div>
      {trend && (
        <div className="mt-4 flex items-center gap-1 text-sm">
          {trendIcon}
          <span className={
            trend.value > 0 ? 'text-success-600' :
            trend.value < 0 ? 'text-danger-600' :
            'text-secondary-500'
          }>
            {trend.value > 0 ? '+' : ''}{trend.value.toFixed(1)}%
          </span>
          <span className="text-secondary-500">{trend.label}</span>
        </div>
      )}
    </div>
  );
}