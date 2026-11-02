/** Header component with page title and actions */

import { Bell, Search, User } from 'lucide-react';
import { useState } from 'react';

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function Header({ title, subtitle, actions }: HeaderProps) {
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-sm border-b border-secondary-200">
      <div className="flex h-16 items-center justify-between px-6">
        <div className="flex-1">
          <h1 className="text-xl font-semibold text-secondary-900">{title}</h1>
          {subtitle && (
            <p className="text-sm text-secondary-500 mt-0.5">{subtitle}</p>
          )}
        </div>

        <div className="flex items-center gap-4">
          {actions}

          {/* Search */}
          <div className="relative hidden sm:block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-secondary-400" aria-hidden="true" />
            <input
              type="search"
              placeholder="Search..."
              className="w-64 pl-10 pr-4 py-2 text-sm bg-secondary-50 border border-secondary-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              aria-label="Search"
            />
          </div>

          {/* Notifications */}
          <div className="relative">
            <button
              onClick={() => setNotificationsOpen(!notificationsOpen)}
              className="relative p-2 rounded-lg text-secondary-500 hover:bg-secondary-100 hover:text-secondary-700 transition-colors"
              aria-label="Notifications"
              aria-expanded={notificationsOpen}
            >
              <Bell className="w-5 h-5" aria-hidden="true" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-danger-500 rounded-full" aria-hidden="true" />
            </button>
            {notificationsOpen && (
              <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl border border-secondary-200 shadow-lg py-2">
                <p className="px-4 py-2 text-sm font-medium text-secondary-700">No new notifications</p>
              </div>
            )}
          </div>

          {/* User menu */}
          <div className="relative">
            <button className="flex items-center gap-2 p-1.5 rounded-lg hover:bg-secondary-100 transition-colors" aria-label="User menu">
              <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center">
                <User className="w-5 h-5 text-primary-600" aria-hidden="true" />
              </div>
              <span className="hidden md:block text-sm font-medium text-secondary-700">Admin</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}