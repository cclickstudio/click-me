'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { label: '대시보드', href: '/admin/dashboard' },
  { label: '회원 관리', href: '/admin/manage-user' },
  { label: '채팅 기록', href: '/admin/chat-log' },
  { label: '고객 문의', href: '/admin/inquiry' },
  { label: '사용량', href: '/admin/check' },
];

export default function AdminSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 bg-[#191F28] min-h-screen flex flex-col shrink-0">
      <div className="px-5 py-5 border-b border-white/10">
        <Link href="/" className="text-white font-bold text-base">ClickMe</Link>
        <span className="block text-[#8B95A1] text-xs mt-0.5">관리자</span>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors ${
                active
                  ? 'bg-white/10 text-white font-medium'
                  : 'text-[#8B95A1] hover:text-white hover:bg-white/5'
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="px-5 py-4 border-t border-white/10">
        <Link href="/" className="text-xs text-[#8B95A1] hover:text-white transition-colors">
          ← 서비스로 이동
        </Link>
      </div>
    </aside>
  );
}
