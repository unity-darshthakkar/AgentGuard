/** Main layout component with sidebar and header */

import { Sidebar } from './Sidebar';
import { Header } from './Header';

interface LayoutProps {
  title: string;
  subtitle?: string;
  headerActions?: React.ReactNode;
  children: React.ReactNode;
}

export function Layout({ title, subtitle, headerActions, children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-secondary-50">
      <Sidebar />
      <div className="lg:ml-64 min-h-screen">
        <Header title={title} subtitle={subtitle} actions={headerActions} />
        <main className="p-6">
          {children}
        </main>
      </div>
    </div>
  );
}