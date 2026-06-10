'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTheme } from './ThemeProvider';

const navItems = [
  { label: '채팅', href: '/chat' },
  { label: '광고 시뮬레이션', href: '/simulation' },
  { label: '광고 제너레이터', href: '/generator' },
  { label: '광고 매니지먼트', href: '/manage' },
];

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export default function Navigation() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-14 bg-white dark:bg-[#1C2333] border-b border-[#E5E8EB] dark:border-[#2D3748] transition-colors">
      <div className="max-w-screen-xl mx-auto h-full px-6 flex items-center justify-between">
        <Link
          href="/"
          className="text-[#3182F6] font-bold text-lg tracking-tight shrink-0"
        >
          ClickMe
        </Link>

        <nav className="flex items-center gap-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                pathname === item.href
                  ? 'text-[#3182F6] bg-[#EBF3FF] dark:bg-[#1E3A5F]'
                  : 'text-[#4E5968] dark:text-[#9CA3AF] hover:text-[#191F28] dark:hover:text-[#F2F4F6] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D]'
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          {/* 다크 모드 토글 */}
          <button
            onClick={toggle}
            className="p-2 rounded-lg text-[#8B95A1] dark:text-[#6B7280] hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] transition-colors"
            aria-label="다크 모드 전환"
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>

          <Link
            href="/sign-in"
            className="px-4 py-2 text-sm font-medium text-[#4E5968] dark:text-[#9CA3AF] hover:text-[#191F28] dark:hover:text-[#F2F4F6] transition-colors"
          >
            로그인
          </Link>
          <Link
            href="/sign-up"
            className="px-4 py-2 text-sm font-medium text-white bg-[#3182F6] rounded-lg hover:bg-[#1B6EEB] transition-colors"
          >
            시작하기
          </Link>
        </div>
      </div>
    </header>
  );
}
