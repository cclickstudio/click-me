// 매니지먼트 화면 공통 셸 — admin일 때만 상단에 조직 impersonation 드롭다운을 얹는다.
'use client';

import { useAuth } from '@/components/AuthProvider';
import { AdminOrgPicker } from '@/components/manage/AdminOrgPicker';

export default function ManageLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  return (
    <>
      {isAdmin && (
        <div className="border-b border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#141922]">
          <div className="max-w-screen-xl mx-auto px-6 py-2.5 flex items-center justify-end gap-2">
            <span className="text-[12px] text-[#8B95A1]">관리자 · 조직 전환</span>
            <AdminOrgPicker />
          </div>
        </div>
      )}
      {children}
    </>
  );
}
