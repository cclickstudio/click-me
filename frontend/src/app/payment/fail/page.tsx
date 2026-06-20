'use client';

import { Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import AppLayout from '@/components/AppLayout';

function FailContent() {
  const params = useSearchParams();
  const code = params.get('code');
  const message = params.get('message');

  return (
    <div className="max-w-screen-md mx-auto px-6 py-16 text-center">
      <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-10">
        <h1 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">결제 실패</h1>
        <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mb-1">
          {message ?? '결제가 완료되지 않았습니다'}
        </p>
        {code && <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] mb-6">코드: {code}</p>}
        <Link
          href="/payment"
          className="inline-block mt-4 px-6 py-3 bg-[#3182F6] text-white text-sm font-medium rounded-xl hover:bg-[#1B6EEB] transition-colors"
        >
          다시 시도
        </Link>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <AppLayout>
      <Suspense fallback={null}>
        <FailContent />
      </Suspense>
    </AppLayout>
  );
}
