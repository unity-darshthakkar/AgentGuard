/** Settings page */

import { useState } from 'react';
import { Bell, Shield, Database, Globe, Save } from 'lucide-react';

interface SettingsSection {
  id: string;
  title: string;
  icon: React.ReactNode;
  description: string;
  content: React.ReactNode;
}

export function Settings() {
  const [activeSection, setActiveSection] = useState('general');

  const sections: SettingsSection[] = [
    {
      id: 'general',
      title: 'General',
      icon: <Globe className="w-5 h-5" />,
      description: 'Application preferences and display settings',
      content: (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-medium text-secondary-900 mb-4">Application</h3>
            <div className="space-y-4">
              <label className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-secondary-900">Dark Mode</p>
                  <p className="text-sm text-secondary-500">Use dark theme (coming soon)</p>
                </div>
                <input type="checkbox" className="w-10 h-6 rounded-full border-secondary-300" disabled />
              </label>
              <label className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-secondary-900">Auto-refresh Dashboard</p>
                  <p className="text-sm text-secondary-500">Automatically refresh data every 30 seconds</p>
                </div>
                <input type="checkbox" defaultChecked className="w-10 h-6 rounded-full border-secondary-300" disabled />
              </label>
              <label className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-secondary-900">Compact Density</p>
                  <p className="text-sm text-secondary-500">Reduce spacing for more data density</p>
                </div>
                <input type="checkbox" className="w-10 h-6 rounded-full border-secondary-300" disabled />
              </label>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-medium text-secondary-900 mb-4">Display</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Default Page Size</label>
                <select className="input w-40" defaultValue="20" disabled>
                  <option value="10">10 rows</option>
                  <option value="20">20 rows</option>
                  <option value="50">50 rows</option>
                  <option value="100">100 rows</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Date Format</label>
                <select className="input w-48" defaultValue="MMM d, yyyy HH:mm" disabled>
                  <option value="MMM d, yyyy HH:mm">Jan 1, 2024 13:30</option>
                  <option value="yyyy-MM-dd HH:mm">2024-01-01 13:30</option>
                  <option value="d MMM yyyy, HH:mm">1 Jan 2024, 13:30</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Currency</label>
                <select className="input w-48" defaultValue="USD" disabled>
                  <option value="USD">USD ($)</option>
                  <option value="EUR">EUR (€)</option>
                  <option value="GBP">GBP (£)</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'notifications',
      title: 'Notifications',
      icon: <Bell className="w-5 h-5" />,
      description: 'Configure alert and notification preferences',
      content: (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-medium text-secondary-900 mb-4">Event Notifications</h3>
            <div className="space-y-3">
              {[
                { title: 'High Risk Transactions', desc: 'Notify when transaction risk score exceeds 70', enabled: true },
                { title: 'Security Events', desc: 'Notify on new security anomalies', enabled: true },
                { title: 'Agent Status Changes', desc: 'Notify when agent status changes', enabled: false },
                { title: 'Daily Summary', desc: 'Receive daily transaction summary email', enabled: false },
              ].map((item, i) => (
                <label key={i} className="flex items-center justify-between p-3 bg-secondary-50 rounded-lg">
                  <div>
                    <p className="font-medium text-secondary-900">{item.title}</p>
                    <p className="text-sm text-secondary-500">{item.desc}</p>
                  </div>
                  <input type="checkbox" defaultChecked={item.enabled} className="w-10 h-6 rounded-full border-secondary-300" disabled />
                </label>
              ))}
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-medium text-secondary-900 mb-4">Notification Channels</h3>
            <div className="space-y-3">
              {[
                { title: 'In-App', desc: 'Show notifications in the application', enabled: true },
                { title: 'Email', desc: 'Send email notifications', enabled: false },
                { title: 'Slack', desc: 'Post to Slack channel (coming soon)', enabled: false },
                { title: 'Webhook', desc: 'Send to custom webhook endpoint', enabled: false },
              ].map((item, i) => (
                <label key={i} className="flex items-center justify-between p-3 bg-secondary-50 rounded-lg">
                  <div>
                    <p className="font-medium text-secondary-900">{item.title}</p>
                    <p className="text-sm text-secondary-500">{item.desc}</p>
                  </div>
                  <input type="checkbox" defaultChecked={item.enabled} className="w-10 h-6 rounded-full border-secondary-300" disabled />
                </label>
              ))}
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'security',
      title: 'Security',
      icon: <Shield className="w-5 h-5" />,
      description: 'Security policies and access control',
      content: (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-lg font-medium text-secondary-900 mb-4">Risk Thresholds</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Auto-block Threshold</label>
                <div className="flex items-center gap-4">
                  <input type="range" min="50" max="100" defaultValue="85" className="flex-1" disabled />
                  <span className="font-mono text-secondary-900 w-16">85</span>
                </div>
                <p className="text-sm text-secondary-500 mt-1">Transactions above this risk score are automatically blocked</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Review Threshold</label>
                <div className="flex items-center gap-4">
                  <input type="range" min="30" max="84" defaultValue="60" className="flex-1" disabled />
                  <span className="font-mono text-secondary-900 w-16">60</span>
                </div>
                <p className="text-sm text-secondary-500 mt-1">Transactions above this risk score require manual review</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Velocity Limit</label>
                <div className="flex items-center gap-4">
                  <input type="number" defaultValue="10" className="input w-24" disabled />
                  <span className="text-secondary-500">transactions per minute</span>
                </div>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-medium text-secondary-900 mb-4">Access Control</h3>
            <div className="space-y-3">
              {[
                { title: 'Require MFA', desc: 'Enforce multi-factor authentication for all users', enabled: true },
                { title: 'Session Timeout', desc: 'Auto-logout after 30 minutes of inactivity', enabled: true },
                { title: 'Audit Logging', desc: 'Log all administrative actions', enabled: true },
                { title: 'IP Allowlist', desc: 'Restrict access to approved IP ranges', enabled: false },
              ].map((item, i) => (
                <label key={i} className="flex items-center justify-between p-3 bg-secondary-50 rounded-lg">
                  <div>
                    <p className="font-medium text-secondary-900">{item.title}</p>
                    <p className="text-sm text-secondary-500">{item.desc}</p>
                  </div>
                  <input type="checkbox" defaultChecked={item.enabled} className="w-10 h-6 rounded-full border-secondary-300" disabled />
                </label>
              ))}
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'integrations',
      title: 'Integrations',
      icon: <Database className="w-5 h-5" />,
      description: 'External service connections and API configuration',
      content: (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-medium text-secondary-900">PayPal Integration</h3>
              <span className="badge badge-warning">Not Configured</span>
            </div>
            <p className="text-secondary-500 mb-4">PayPal credentials are deployment-managed and cannot be edited in the browser.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Client ID</label>
                <input type="text" className="input" placeholder="Enter PayPal Client ID" disabled />
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">Client Secret</label>
                <input type="password" className="input" placeholder="Enter PayPal Client Secret" disabled />
              </div>
            </div>
            <div className="mt-4">
              <label className="block text-sm font-medium text-secondary-700 mb-1">Environment</label>
              <select className="input w-48" disabled>
                <option value="sandbox">Sandbox</option>
                <option value="live">Live</option>
              </select>
            </div>
            <button className="btn-primary mt-4" disabled>
              <Save className="w-4 h-4" />
              Save Configuration
            </button>
          </div>

          <div className="card p-6">
            <h3 className="text-lg font-medium text-secondary-900 mb-4">Database</h3>
            <div className="space-y-4">
              <div className="p-4 bg-secondary-50 rounded-lg">
                <p className="font-medium text-secondary-900">Current: SQLite (Development)</p>
                <p className="text-sm text-secondary-500">File: ./agentguard.db</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary-700 mb-1">PostgreSQL Connection String</label>
                <input type="text" className="input" placeholder="postgresql://user:pass@host:5432/db" disabled />
                <p className="text-sm text-secondary-500 mt-1">Deployment-managed setting; not available in this console.</p>
              </div>
            </div>
          </div>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="flex gap-6">
        {/* Sidebar Navigation */}
        <div className="w-56 flex-shrink-0">
          <nav className="space-y-1" aria-label="Settings navigation">
            {sections.map(section => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-colors ${
                  activeSection === section.id
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-secondary-600 hover:bg-secondary-100 hover:text-secondary-900'
                }`}
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                  activeSection === section.id
                    ? 'bg-primary-100 text-primary-600'
                    : 'bg-secondary-100 text-secondary-500'
                }`}>
                  {section.icon}
                </div>
                <div>
                  <p className="font-medium">{section.title}</p>
                  <p className="text-xs text-secondary-500">{section.description}</p>
                </div>
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1">
          {sections.find(s => s.id === activeSection)?.content}
        </div>
      </div>

      {/* Demo Notice - compact */}
      <div className="mt-4 p-3 bg-primary-50 border border-primary-200 rounded-lg">
        <p className="text-xs text-primary-700">
          Settings requiring deployment secrets or backend infrastructure are not available in this console.
        </p>
      </div>
    </>
  );
}
