'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from './AuthProvider';
import Sidebar from './Sidebar';
import ProjectPanel from './ProjectPanel';
import CompanyPanel from './CompanyPanel';
import AdminPanel from './AdminPanel';
import ChangePasswordModal from './ChangePasswordModal';
import NotificationBell from './manage/notifications/NotificationBell';

// COMPANY 계정이 막아야 하는 경로 — 채팅·시뮬/제너 실행 + 내 정보 관리(USER 전용)
// 정확 일치만 차단한다 — /simulation/[id](결과)·/generations/[id] 상세, /projects 등은 허용.
const COMPANY_BLOCKED = ['/chat', '/simulation', '/generator', '/profile'];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  const [pwDismissed, setPwDismissed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false); // 모바일 사이드바 드로어

  useEffect(() => {
    const stored = localStorage.getItem('panelCollapsed');
    if (stored === 'true') setPanelCollapsed(true);
  }, []);

  // 라우트 이동 시 모바일 드로어 닫기.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

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

  if (companyBlocked) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const role = user?.role;
  // 데스크톱(md+)에만 좌측 패널 폭만큼 패딩 — 모바일은 풀폭(드로어로 사이드바 접근).
  const mainLeft = panelCollapsed ? 'md:pl-[274px]' : 'md:pl-[512px]';

  // 역할별 좌측 패널 — ADMIN: 회사>팀>프로젝트 / COMPANY: 조직 전체(ALL·TEAM, 조회) / USER: 내 팀 프로젝트
  const Panel =
    role === 'ADMIN' ? AdminPanel : role === 'COMPANY' ? CompanyPanel : ProjectPanel;

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] transition-colors">
      {/* 모바일 햄버거 — 사이드바 드로어 토글(데스크톱 숨김) */}
      <button
        type="button"
        onClick={() => setMobileNavOpen(true)}
        aria-label="메뉴 열기"
        className="md:hidden fixed top-3 left-3 z-50 w-10 h-10 flex items-center justify-center rounded-lg bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] shadow-sm"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      {/* 모바일 드로어 배경 오버레이 */}
      {mobileNavOpen && (
        <div
          onClick={() => setMobileNavOpen(false)}
          className="md:hidden fixed inset-0 z-30 bg-black/40"
          aria-hidden
        />
      )}
      <Sidebar mobileOpen={mobileNavOpen} />
      <NotificationBell />
      {/* 좌측 컨텍스트 패널 — 모바일에선 숨김(메인 콘텐츠가 선택 UI 제공) */}
      <div className="max-md:hidden">
        <Panel collapsed={panelCollapsed} onToggle={togglePanel} />
      </div>
      <main className={`${mainLeft} min-h-screen transition-all duration-200`}>
        {children}
      </main>
      {user?.must_change_password && !pwDismissed && (
        <ChangePasswordModal onClose={() => setPwDismissed(true)} />
      )}
    </div>
  );
}
