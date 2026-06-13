'use client';

import { usePathname } from 'next/navigation';
import { useAuth } from './AuthProvider';
import PendingScreen from './PendingScreen';
import Sidebar from './Sidebar';
import ProjectPanel from './ProjectPanel';

const PANEL_PATHS = ['/chat', '/simulation', '/generator', '/manage', '/simulations', '/generations'];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const showPanel = PANEL_PATHS.some((p) => pathname.startsWith(p));

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (user?.status === 'PENDING') return <PendingScreen />;

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] transition-colors">
      <Sidebar />
      {showPanel && <ProjectPanel />}
      <main className={showPanel ? 'pl-[464px] min-h-screen' : 'pl-56 min-h-screen'}>
        {children}
      </main>
    </div>
  );
}
