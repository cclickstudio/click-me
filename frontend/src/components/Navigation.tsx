'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { label: '채팅', href: '/chat' },
  { label: '시뮬레이터', href: '/simulation' },
  { label: '광고 제너레이터', href: '/generator' },
  { label: '광고 매니지먼트', href: '/manage' },
];

export default function Navigation() {
  const pathname = usePathname();

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-14 bg-white border-b border-[#E5E8EB]">
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
                  ? 'text-[#3182F6] bg-[#EBF3FF]'
                  : 'text-[#4E5968] hover:text-[#191F28] hover:bg-[#F2F4F6]'
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2 shrink-0">
          <Link
            href="/sign-in"
            className="px-4 py-2 text-sm font-medium text-[#4E5968] hover:text-[#191F28] transition-colors"
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
