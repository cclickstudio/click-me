'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useTheme } from './ThemeProvider';
import { useAuth } from './AuthProvider';
import { getToken } from '@/lib/authApi';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const mainNav = [
  {
    label: '대시보드', href: '/dashboard',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></svg>,
  },
  {
    label: '프로젝트', href: '/projects',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /></svg>,
  },
  {
    label: '채팅', href: '/chat',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>,
  },
  {
    label: '광고 시뮬레이션', href: '/simulation',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>,
  },
  {
    label: '광고 제너레이터', href: '/generator',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>,
  },
  {
    label: '광고 매니지먼트', href: '/manage',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></svg>,
  },
];

const adminNav = [
  {
    label: '기업 승인', href: '/admin/companies',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 12l2 2 4-4" /><rect x="2" y="7" width="20" height="14" rx="2" /><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" /></svg>,
  },
  {
    label: '채팅 내역', href: '/admin/chats',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>,
  },
  {
    label: '시뮬레이션 내역', href: '/admin/simulations',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" /></svg>,
  },
  {
    label: '제너레이터 내역', href: '/admin/generations',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>,
  },
];

const companyNav = [
  {
    label: '멤버 승인', href: '/company/members',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><line x1="19" y1="8" x2="19" y2="14" /><line x1="22" y1="11" x2="16" y2="11" /></svg>,
  },
  {
    label: '시뮬레이션 내역', href: '/company/simulations',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polygon points="10 8 16 12 10 16 10 8" /></svg>,
  },
  {
    label: '제너레이터 내역', href: '/company/generations',
    icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" /></svg>,
  },
];

function NavItem({ href, label, icon, active, badge }: { href: string; label: string; icon: React.ReactNode; active: boolean; badge?: number }) {
  return (
    <Link href={href}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
        active ? 'bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]'
               : 'text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-[#191F28] dark:hover:text-[#F2F4F6]'
      }`}
    >
      <span className={active ? 'text-[#3182F6]' : ''}>{icon}</span>
      <span className="flex-1">{label}</span>
      {badge != null && badge > 0 && (
        <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-[#F74D4D] text-white text-[10px] font-bold leading-none">
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </Link>
  );
}

function SectionLabel({ label }: { label: string }) {
  return <p className="px-3 pt-3 pb-1 text-[10px] font-semibold text-[#B0B8C1] dark:text-[#4B5563] uppercase tracking-wider">{label}</p>;
}

export default function Sidebar() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const router = useRouter();
  const [pendingCompanyCount, setPendingCompanyCount] = useState(0);
  const [pendingMemberCount, setPendingMemberCount] = useState(0);

  const handleLogout = () => { logout(); router.push('/'); };

  const isAdmin = user?.role === 'ADMIN';
  const isCompany = user?.role === 'COMPANY';
  const isOrgMember = user?.role === 'COMPANY' || user?.role === 'USER';

  useEffect(() => {
    if (!isAdmin) return;
    fetch(`${API_BASE}/api/admin/pending-companies`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setPendingCompanyCount(data.length); })
      .catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    if (!isCompany) return;
    fetch(`${API_BASE}/api/company/pending-members`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setPendingMemberCount(data.length); })
      .catch(() => {});
  }, [isCompany]);

  return (
    <aside className="fixed top-0 left-0 h-full w-56 bg-white dark:bg-[#1C2333] border-r border-[#E5E8EB] dark:border-[#2D3748] flex flex-col z-40 transition-colors">
      {/* 로고 */}
      <div className="h-14 flex items-center px-5 border-b border-[#E5E8EB] dark:border-[#2D3748] shrink-0">
        <Link href="/dashboard" className="text-[#3182F6] font-bold text-lg tracking-tight">ClickMe</Link>
      </div>

      {/* 네비게이션 */}
      <nav className="flex-1 px-3 py-3 overflow-y-auto space-y-0.5">
        {mainNav.map((item) => (
          <NavItem key={item.href} {...item} active={pathname === item.href} />
        ))}

        {/* ADMIN 전용 섹션 */}
        {isAdmin && (
          <>
            <SectionLabel label="관리자" />
            {adminNav.map((item) => (
              <NavItem
                key={item.href}
                {...item}
                active={pathname === item.href}
                badge={item.href === '/admin/companies' ? pendingCompanyCount : undefined}
              />
            ))}
          </>
        )}

        {/* COMPANY 전용 섹션 */}
        {isOrgMember && (
          <>
            <SectionLabel label="기업 관리" />
            {companyNav
              .filter((item) => isCompany || item.href !== '/company/members')
              .map((item) => (
                <NavItem
                  key={item.href}
                  {...item}
                  active={pathname === item.href}
                  badge={item.href === '/company/members' ? pendingMemberCount : undefined}
                />
              ))}
          </>
        )}
      </nav>

      {/* 하단 */}
      <div className="px-4 py-4 border-t border-[#E5E8EB] dark:border-[#2D3748] shrink-0 space-y-1">
        {user ? (
          <div className="px-3 py-2.5 rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] mb-1">
            <p className="text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6] truncate">{user.name}</p>
            <p className="text-[10px] text-[#8B95A1] dark:text-[#6B7280] truncate">{user.email}</p>
            <span className="inline-block mt-1 text-[9px] font-medium px-1.5 py-0.5 rounded bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]">
              {user.role}
            </span>
          </div>
        ) : (
          <Link href="/sign-in"
            className="flex items-center gap-2 px-3 py-2.5 w-full rounded-xl text-sm font-medium text-[#3182F6] hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors">
            로그인
          </Link>
        )}

        <button onClick={toggle}
          className="flex items-center gap-3 px-3 py-2.5 w-full rounded-xl text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors">
          {theme === 'dark'
            ? <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" /></svg>
            : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
          }
          {theme === 'dark' ? '라이트 모드' : '다크 모드'}
        </button>

        {user && (
          <button onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2.5 w-full rounded-xl text-sm font-medium text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] hover:text-red-400 transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            로그아웃
          </button>
        )}
      </div>
    </aside>
  );
}
