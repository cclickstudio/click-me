'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from './AuthProvider';
import PendingScreen from './PendingScreen';
import Sidebar from './Sidebar';
import ProjectPanel from './ProjectPanel';
import CompanyPanel from './CompanyPanel';
import AdminPanel from './AdminPanel';
import ChangePasswordModal from './ChangePasswordModal';

// COMPANY 계정이 막아야 하는 경로 — 채팅·시뮬/제너 실행 + 내 정보 관리(USER 전용)
// 정확 일치만 차단한다 — /simulation/[id](결과)·/generations/[id] 상세, /projects 등은 허용.
const COMPANY_BLOCKED = ['/chat', '/simulation', '/generator', '/profile'];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [pwDismissed, setPwDismissed] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('panelCollapsed');
    if (stored === 'true') setPanelCollapsed(true);
  }, []);

  // COMPANY는 채팅·시뮬/제너 실행만 차단(프로젝트·상세·삭제·팀 관리는 허용)
  // 정확 일치만 — /simulation/[id](결과 대시보드)는 허용해야 COMPANY도 시뮬 결과를 본다.
  const companyBlocked =
    user?.role === 'COMPANY' && COMPANY_BLOCKED.includes(pathname);
  useEffect(() => {
    if (!loading && companyBlocked) router.replace('/dashboard');
  }, [loading, companyBlocked, router]);

  // 미로그인 가드 — 토큰 없거나 만료(user 없음)면 진입 라우트(/sign-in)로 튕김.
  useEffect(() => {
    if (!loading && !user) router.replace('/sign-in');
  }, [loading, user, router]);

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

  // 미로그인 — 안내를 잠깐 띄우고 위 useEffect가 /sign-in으로 이동시킨다.
  if (!user) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex flex-col items-center justify-center gap-3">
        <p className="text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF]">
          로그인이 필요한 서비스입니다.
        </p>
        <div className="w-6 h-6 border-2 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (user?.status === 'PENDING') return <PendingScreen />;

  if (companyBlocked) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const role = user?.role;
  const mainLeft = panelCollapsed ? 'pl-[274px]' : 'pl-[512px]';

  // 역할별 좌측 패널 — ADMIN: 회사>팀>프로젝트 / COMPANY: 조직 전체(ALL·TEAM, 조회) / USER: 내 팀 프로젝트
  const Panel =
    role === 'ADMIN' ? AdminPanel : role === 'COMPANY' ? CompanyPanel : ProjectPanel;

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] transition-colors">
      <Sidebar />
      <Panel collapsed={panelCollapsed} onToggle={togglePanel} />
      <main className={`${mainLeft} min-h-screen transition-all duration-200`}>
        {children}
      </main>
      {user?.must_change_password && !pwDismissed && (
        <ChangePasswordModal onClose={() => setPwDismissed(true)} />
      )}
    </div>
  );
}
