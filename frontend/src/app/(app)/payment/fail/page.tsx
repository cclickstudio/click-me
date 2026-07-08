'use client';

import { Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
function FailContent() {
  const params = useSearchParams();
  const code = params.get('code');
  const message = params.get('message');

  return (
    <div className="max-w-screen-md mx-auto px-6 py-16 text-center">
      <div className="bg-card border border-line rounded-2xl p-10">
        <h1 className="text-xl font-bold text-ink mb-2">결제 실패</h1>
        <p className="text-sm text-ink-tertiary mb-1">
          {message ?? '결제가 완료되지 않았습니다'}
        </p>
        {code && <p className="text-xs text-ink-muted mb-6">코드: {code}</p>}
        <Link
          href="/payment"
          className="inline-block mt-4 px-6 py-3 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:bg-primary-hover transition-colors"
        >
          다시 시도
        </Link>
      </div>
    </div>
  );
}

export default function Page() {
  return (
      <Suspense fallback={null}>
        <FailContent />
      </Suspense>
  );
}
