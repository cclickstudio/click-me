// /admin/* 접근을 ADMIN 역할로 제한 — 레이아웃 셸은 상위 (app)/layout의 AppLayout을 그대로 사용한다.
'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  // 미로그인은 상위 AppLayout이 이미 /sign-in으로 보낸다. 여기선 로그인했지만 ADMIN이 아닌 경우만 차단.
  useEffect(() => {
    if (!loading && user && user.role !== 'ADMIN') router.replace('/dashboard');
  }, [loading, user, router]);

  // ADMIN 확정 전에는 admin 콘텐츠를 렌더하지 않는다(비-ADMIN은 위에서 리다이렉트).
  if (loading || user?.role !== 'ADMIN') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return <>{children}</>;
}
