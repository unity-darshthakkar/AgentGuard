/** Sidebar navigation component */

import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  CreditCard,
  ShieldAlert,
  Shield,
  Settings,
  Info,
  Siren,
} from 'lucide-react';

const navigation = [
  { name: 'Overview', href: '/', icon: LayoutDashboard },
  { name: 'Agents', href: '/agents', icon: Users },
  { name: 'Transactions', href: '/transactions', icon: CreditCard },
  { name: 'Authorization Decisions', href: '/authorization-decisions', icon: Shield },
  { name: 'Security Events', href: '/security-events', icon: ShieldAlert },
  { name: 'Attack Simulator', href: '/attack-simulator', icon: Siren },
  { name: 'Settings', href: '/settings', icon: Settings },
  { name: 'About', href: '/about', icon: Info },
];

export function Sidebar() {
  const location = useLocation();
  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 bg-white border-r border-secondary-200">
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div
          className="flex h-16 items-center px-4 border-b border-secondary-200"
        >
            <NavLink to="/" className="flex items-center gap-2 font-semibold text-lg text-primary-600">
              <svg className="w-8 h-8" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="32" height="32" rx="8" fill="currentColor"/>
                <path d="M8 12h16M8 16h12M8 20h8" stroke="white" stroke-width="2" stroke-linecap="round"/>
                <path d="M20 16v8" stroke="white" stroke-width="2" stroke-linecap="round"/>
                <circle cx="24" cy="24" r="4" fill="#ef4444"/>
              </svg>
              <span>AgentGuard</span>
            </NavLink>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1" aria-label="Main navigation">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href || (item.href !== '/' && location.pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <NavLink
                key={item.name}
                to={item.href}
                className={({ isActive: active }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    active
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-secondary-600 hover:bg-secondary-100 hover:text-secondary-900'
                  }`
                }
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="p-4 border-t border-secondary-200">
          <p className="text-xs text-secondary-500 text-center">
            Security operations console
          </p>
        </div>
      </div>
    </aside>
  );
}
