'use client';

import { useEffect, useState } from 'react';
import { useAuth } from './AuthProvider';
import PendingScreen from './PendingScreen';
import Sidebar from './Sidebar';
import ProjectPanel from './ProjectPanel';
import CompanyPanel from './CompanyPanel';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const [panelCollapsed, setPanelCollapsed] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('panelCollapsed');
    if (stored === 'true') setPanelCollapsed(true);
  }, []);

  const togglePanel = () => {
    setPanelCollapsed(v => {
      const next = !v;
      localStorage.setItem('panelCollapsed', String(next));
      return next;
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (user?.status === 'PENDING') return <PendingScreen />;

  const isAdmin = user?.role === 'ADMIN';
  const mainLeft = panelCollapsed ? 'pl-[274px]' : 'pl-[464px]';

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] transition-colors">
      <Sidebar />
      {isAdmin
        ? <CompanyPanel collapsed={panelCollapsed} onToggle={togglePanel} />
        : <ProjectPanel collapsed={panelCollapsed} onToggle={togglePanel} />
      }
      <main className={`${mainLeft} min-h-screen transition-all duration-200`}>
        {children}
      </main>
    </div>
  );
}
