/** Tests for KPICard component */

import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { KPICard } from './KPICard';

describe('KPICard', () => {
  it('renders title, value, and subtitle', () => {
    render(
      <KPICard
        title="Total Agents"
        value={12}
        subtitle="Active: 8"
        icon={null}
        trend={{ value: 2, label: 'vs last week' }}
      />
    );

    expect(screen.getByText('Total Agents')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('Active: 8')).toBeInTheDocument();
    expect(screen.getByText('vs last week')).toBeInTheDocument();
  });

  it('renders positive trend value', () => {
    render(
      <KPICard
        title="Total Agents"
        value={12}
        subtitle="Active: 8"
        trend={{ value: 2, label: 'vs last week' }}
      />
    );

    // Check that the trend value (+2.0%) is rendered
    expect(screen.getByText('+2.0%')).toBeInTheDocument();
  });

  it('renders negative trend value', () => {
    render(
      <KPICard
        title="Total Agents"
        value={12}
        subtitle="Active: 8"
        trend={{ value: -2, label: 'vs last week' }}
      />
    );

    // Check that the trend value (-2.0%) is rendered
    expect(screen.getByText('-2.0%')).toBeInTheDocument();
  });

  it('renders zero trend value', () => {
    render(
      <KPICard
        title="Total Agents"
        value={12}
        subtitle="Active: 8"
        trend={{ value: 0, label: 'vs last week' }}
      />
    );

    // Check that the trend value (0.0%) is rendered
    expect(screen.getByText('0.0%')).toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    render(
      <KPICard
        title="Total Agents"
        value={12}
        subtitle="Active: 8"
        icon={<span data-testid="icon">Icon</span>}
      />
    );

    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('renders without trend when not provided', () => {
    render(
      <KPICard
        title="Total Agents"
        value={12}
        subtitle="Active: 8"
      />
    );

    expect(screen.queryByText('vs last week')).not.toBeInTheDocument();
    expect(screen.queryByText('%')).not.toBeInTheDocument();
  });
});