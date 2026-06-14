'use client';

import { useAuth } from './AuthProvider';
import { useRouter } from 'next/navigation';

export default function PendingScreen() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => { logout(); router.push('/'); };

  const isCompany = user?.role === 'COMPANY';

  return (
    <div className="min-h-screen bg-[#F9FAFB] dark:bg-[#0F1117] flex flex-col items-center justify-center p-6 transition-colors">
      <div className="w-full max-w-md text-center">
        <div className="w-16 h-16 rounded-2xl bg-[#FFF8E6] dark:bg-[#2D2000] flex items-center justify-center mx-auto mb-6">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#F4A100" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>

        <h1 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">승인 대기 중</h1>
        <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] leading-relaxed mb-1">
          {isCompany
            ? '기업 계정 가입 요청이 접수되었습니다.'
            : '소속 회사의 승인을 기다리고 있습니다.'}
        </p>
        <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] leading-relaxed mb-8">
          {isCompany
            ? '관리자가 검토 후 승인하면 서비스를 이용할 수 있습니다.'
            : '회사 담당자가 승인하면 서비스를 이용할 수 있습니다.'}
        </p>

        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5 text-left space-y-2 mb-8">
          <div className="flex justify-between text-sm">
            <span className="text-[#8B95A1] dark:text-[#6B7280]">이름</span>
            <span className="text-[#191F28] dark:text-[#F2F4F6] font-medium">{user?.name}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-[#8B95A1] dark:text-[#6B7280]">이메일</span>
            <span className="text-[#191F28] dark:text-[#F2F4F6]">{user?.email}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-[#8B95A1] dark:text-[#6B7280]">계정 유형</span>
            <span className="text-[#191F28] dark:text-[#F2F4F6]">{isCompany ? '기업' : '개인'}</span>
          </div>
        </div>

        <button onClick={handleLogout}
          className="text-sm text-[#8B95A1] dark:text-[#6B7280] hover:text-[#191F28] dark:hover:text-[#F2F4F6] transition-colors">
          로그아웃
        </button>
      </div>
    </div>
  );
}
