'use client';

// 좌측 고정 사이드바 — 역할별 네비게이션·테마 토글·계정 카드. 토큰+lucide 기반 리스킨.

import Link from 'next/link';
import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  MessageSquare,
  Users,
  Sparkles,
  BarChart3,
  ChevronDown,
  ShieldCheck,
  History,
  Building2,
  UserCog,
  Sun,
  Moon,
  LogOut,
} from 'lucide-react';
import { useTheme } from './ThemeProvider';
import { useAuth } from './AuthProvider';
import CreditBalance from './CreditBalance';

const iconProps = { size: 18, strokeWidth: 1.8 } as const;

const mainNav = [
  { label: '대시보드', href: '/dashboard', icon: <LayoutDashboard {...iconProps} /> },
  { label: '채팅', href: '/chat', icon: <MessageSquare {...iconProps} /> },
  { label: '광고 제너레이터', href: '/generator', icon: <Sparkles {...iconProps} /> },
  { label: '광고 시뮬레이션', href: '/simulation', icon: <Users {...iconProps} /> },
  { label: '광고 매니지먼트', href: '/manage', icon: <BarChart3 {...iconProps} /> },
];

// 광고 매니지먼트 하위 메뉴 — 부모는 토글(자체 페이지 없음), 실제 화면은 여기로.
const manageChildren = [
  { label: '홈', href: '/manage' },
  { label: '캠페인', href: '/manage/campaigns' },
  { label: '모니터링', href: '/manage/monitoring' },
  { label: '이상 감지', href: '/manage/anomaly' },
  { label: '예산 관리', href: '/manage/budget' },
  { label: '성과 비교', href: '/manage/compare' },
  { label: '신뢰도', href: '/manage/reliability' },
  { label: '연동', href: '/manage/connect' },
];

// ADMIN 전용 — "관리"(조직·회원) / "내역"(시뮬·제너·채팅) 두 아코디언 섹션.
const adminManageChildren = [
  { label: '조직 관리', href: '/admin/companies' },
  { label: '회원 관리', href: '/admin/manage-user' },
  { label: '문의 관리', href: '/admin/inquiry' },
];
const adminHistoryChildren = [
  { label: '시뮬레이션 내역', href: '/simulations' },
  { label: '제너레이터 내역', href: '/admin/generations' },
  { label: '채팅 내역', href: '/admin/chats' },
];

// COMPANY 전용 — ADMIN과 동일 구조(관리/내역 아코디언), 데이터는 자기 조직으로 스코프.
const companyManageChildren = [
  { label: '팀 관리', href: '/company/teams' },
  { label: '프로젝트 관리', href: '/company/projects' },
  { label: '직원 관리', href: '/company/members' },
  { label: '크레딧 관리', href: '/company/credits' },
];
const companyHistoryChildren = [
  { label: '시뮬레이션 내역', href: '/simulations' },
  { label: '제너레이터 내역', href: '/company/generations' },
  { label: '채팅 내역', href: '/company/chats' },
];

const adminManageIcon = <ShieldCheck {...iconProps} />;
const adminHistoryIcon = <History {...iconProps} />;

// COMPANY는 채팅·시뮬레이션 실행·제너레이터 실행 메뉴 숨김
const COMPANY_HIDDEN_NAV = ['/chat', '/simulation', '/generator'];

function NavItem({ href, label, icon, active }: { href: string; label: string; icon: React.ReactNode; active: boolean }) {
  return (
    <Link href={href}
      className={`group relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-primary-subtle text-primary before:absolute before:left-0 before:top-1/2 before:h-5 before:w-1 before:-translate-y-1/2 before:rounded-r-full before:bg-primary'
          : 'text-ink-secondary hover:bg-accent hover:text-ink'
      }`}
    >
      <span className={active ? 'text-primary' : 'text-ink-tertiary group-hover:text-ink-secondary transition-colors'}>{icon}</span>
      <span className="flex-1">{label}</span>
    </Link>
  );
}

function SubNavItem({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link href={href}
      className={`flex items-center gap-2.5 pl-11 pr-3 py-2 rounded-lg text-sm transition-colors ${
        active
          ? 'bg-primary-subtle text-primary font-medium'
          : 'text-ink-tertiary hover:bg-accent hover:text-ink'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full transition-colors ${active ? 'bg-primary' : 'bg-current opacity-50'}`} />
      <span className="flex-1">{label}</span>
    </Link>
  );
}

function SectionLabel({ label }: { label: string }) {
  return <p className="px-3 pt-4 pb-1 text-[10px] font-semibold text-ink-muted uppercase tracking-wider">{label}</p>;
}

// 하위 메뉴를 토글하는 아코디언 섹션(부모는 자체 페이지 없음) — 광고 매니지먼트와 동일 패턴.
function NavAccordion({
  label,
  icon,
  items,
  open,
  onToggle,
  pathname,
}: {
  label: string;
  icon: React.ReactNode;
  items: { label: string; href: string }[];
  open: boolean;
  onToggle: () => void;
  pathname: string;
}) {
  const sectionActive = items.some((c) => c.href === pathname);
  return (
    <div>
      <button type="button" onClick={onToggle}
        aria-label={`${label} 하위 메뉴 토글`} aria-expanded={open}
        className={`group flex items-center w-full rounded-lg text-sm font-medium transition-colors ${
          sectionActive ? 'text-primary' : 'text-ink-secondary hover:bg-accent hover:text-ink'
        }`}
      >
        <span className="flex items-center gap-3 flex-1 pl-3 py-2.5">
          <span className={sectionActive ? 'text-primary' : 'text-ink-tertiary group-hover:text-ink-secondary transition-colors'}>{icon}</span>
          <span>{label}</span>
        </span>
        <span className="px-3 py-2.5 text-ink-tertiary">
          <ChevronDown size={14} strokeWidth={2} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>
      {open && (
        <div className="mt-0.5 space-y-0.5">
          {items.map((c) => (
            <SubNavItem key={c.href} href={c.href} label={c.label} active={pathname === c.href} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Sidebar({ mobileOpen = false }: { mobileOpen?: boolean }) {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const router = useRouter();
  const [manageOpen, setManageOpen] = useState(pathname.startsWith('/manage'));
  const [adminManageOpen, setAdminManageOpen] = useState(
    adminManageChildren.some((c) => c.href === pathname),
  );
  const [adminHistoryOpen, setAdminHistoryOpen] = useState(
    adminHistoryChildren.some((c) => c.href === pathname),
  );
  const [companyManageOpen, setCompanyManageOpen] = useState(
    companyManageChildren.some((c) => c.href === pathname),
  );
  const [companyHistoryOpen, setCompanyHistoryOpen] = useState(
    companyHistoryChildren.some((c) => c.href === pathname),
  );

  const handleLogout = () => { logout(); router.push('/'); };

  const isAdmin = user?.role === 'ADMIN';
  const isCompany = user?.role === 'COMPANY';
  const isUser = user?.role === 'USER';

  return (
    <aside
      className={`fixed top-0 left-0 h-full w-56 bg-card border-r border-line flex flex-col z-40 transition-transform duration-200 md:translate-x-0 ${
        mobileOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full'
      }`}
    >
      {/* 로고 */}
      <div className="h-14 flex items-center px-5 border-b border-line shrink-0">
        <Link href="/dashboard" className="flex items-center gap-2 text-primary font-bold text-lg tracking-tight">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo/logo-mark.png" alt="" className="h-7 w-7 rounded-md shrink-0" />
          ClickMe
        </Link>
      </div>

      {/* 네비게이션 */}
      <nav className="flex-1 px-3 py-3 overflow-y-auto space-y-0.5">
        {/* COMPANY는 채팅·시뮬/제너 실행 메뉴만 숨김 (대시보드·매니지먼트·프로젝트는 허용) */}
        {mainNav
          .filter((item) => !isCompany || !COMPANY_HIDDEN_NAV.includes(item.href))
          .map((item) => {
            // 광고 매니지먼트 — 카테고리. 누르면 하위 메뉴만 토글(자체 페이지 없음).
            if (item.href === '/manage') {
              const sectionActive = pathname.startsWith('/manage');
              return (
                <div key="/manage">
                  <button type="button" onClick={() => setManageOpen((o) => !o)}
                    aria-label="광고 매니지먼트 하위 메뉴 토글" aria-expanded={manageOpen}
                    className={`group flex items-center w-full rounded-lg text-sm font-medium transition-colors ${
                      sectionActive ? 'text-primary' : 'text-ink-secondary hover:bg-accent hover:text-ink'
                    }`}
                  >
                    <span className="flex items-center gap-3 flex-1 pl-3 py-2.5">
                      <span className={sectionActive ? 'text-primary' : 'text-ink-tertiary group-hover:text-ink-secondary transition-colors'}>{item.icon}</span>
                      <span>{item.label}</span>
                    </span>
                    <span className="px-3 py-2.5 text-ink-tertiary">
                      <ChevronDown size={14} strokeWidth={2} className={`transition-transform ${manageOpen ? 'rotate-180' : ''}`} />
                    </span>
                  </button>
                  {manageOpen && (
                    <div className="mt-0.5 space-y-0.5">
                      {manageChildren.map((c) => (
                        <SubNavItem key={c.href} href={c.href} label={c.label} active={pathname === c.href} />
                      ))}
                    </div>
                  )}
                </div>
              );
            }
            const active =
              pathname === item.href ||
              (item.href === '/chat' && pathname.startsWith('/chat/')) ||
              (item.href === '/simulation' && pathname.startsWith('/simulation/')) ||
              (item.href === '/generator' && pathname.startsWith('/generations/'));
            return <NavItem key={item.href} {...item} active={active} />;
          })}

        {/* ADMIN 전용 섹션 — 관리(조직·회원) / 내역(시뮬·제너·채팅) 두 아코디언 */}
        {isAdmin && (
          <>
            <SectionLabel label="관리자" />
            <NavAccordion
              label="관리" icon={adminManageIcon}
              items={adminManageChildren}
              open={adminManageOpen} onToggle={() => setAdminManageOpen((o) => !o)}
              pathname={pathname}
            />
            <NavAccordion
              label="내역" icon={adminHistoryIcon}
              items={adminHistoryChildren}
              open={adminHistoryOpen} onToggle={() => setAdminHistoryOpen((o) => !o)}
              pathname={pathname}
            />
          </>
        )}

        {/* COMPANY 전용 섹션 — ADMIN과 동일하게 관리/내역 두 아코디언(자기 조직 스코프) */}
        {isCompany && (
          <>
            <SectionLabel label="기업 관리" />
            <NavAccordion
              label="관리" icon={adminManageIcon}
              items={companyManageChildren}
              open={companyManageOpen} onToggle={() => setCompanyManageOpen((o) => !o)}
              pathname={pathname}
            />
            <NavAccordion
              label="내역" icon={adminHistoryIcon}
              items={companyHistoryChildren}
              open={companyHistoryOpen} onToggle={() => setCompanyHistoryOpen((o) => !o)}
              pathname={pathname}
            />
          </>
        )}

        {/* USER 전용 — 내 조직 / 내 정보 관리 */}
        {isUser && (
          <>
            <SectionLabel label="계정" />
            <NavItem
              href="/my-org"
              label="내 조직"
              active={pathname === '/my-org'}
              icon={<Building2 {...iconProps} />}
            />
            <NavItem
              href="/profile"
              label="내 정보 관리"
              active={pathname === '/profile'}
              icon={<UserCog {...iconProps} />}
            />
          </>
        )}
      </nav>

      {/* 하단 */}
      <div className="px-4 py-4 border-t border-line shrink-0 space-y-1">
        {/* ClickMe 크레딧 잔액 — 광고 집행 한도. 충전(/payment)로 이동. ADMIN(슈퍼유저)은 미표시. */}
        {user && !isAdmin && (
          <div className="mb-2">
            <CreditBalance />
          </div>
        )}
        {user ? (
          <div className="px-3 py-2.5 rounded-lg bg-surface-1 mb-1">
            <p className="text-xs font-semibold text-ink truncate">{user.name}</p>
            <p className="text-[10px] text-ink-tertiary truncate">{user.login_id}</p>
            <span className="inline-block mt-1 text-[9px] font-medium px-1.5 py-0.5 rounded bg-primary-subtle text-primary">
              {user.role}
            </span>
          </div>
        ) : (
          <Link href="/sign-in"
            className="flex items-center gap-2 px-3 py-2.5 w-full rounded-lg text-sm font-medium text-primary hover:bg-primary-subtle transition-colors">
            로그인
          </Link>
        )}

        <button onClick={toggle}
          className="flex items-center gap-3 px-3 py-2.5 w-full rounded-lg text-sm font-medium text-ink-secondary hover:bg-accent hover:text-ink transition-colors">
          {theme === 'dark' ? <Sun size={16} strokeWidth={2} /> : <Moon size={16} strokeWidth={2} />}
          {theme === 'dark' ? '라이트 모드' : '다크 모드'}
        </button>

        {user && (
          <button onClick={handleLogout}
            className="flex items-center gap-3 px-3 py-2.5 w-full rounded-lg text-sm font-medium text-ink-tertiary hover:bg-danger-subtle hover:text-danger transition-colors">
            <LogOut size={16} strokeWidth={2} />
            로그아웃
          </button>
        )}
      </div>
    </aside>
  );
}
