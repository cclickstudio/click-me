'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';

function SuccessContent() {
  const params = useSearchParams();
  const [status, setStatus] = useState<'confirming' | 'done' | 'error'>('confirming');
  const [balance, setBalance] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const confirmedRef = useRef(false);

  useEffect(() => {
    const paymentKey = params.get('paymentKey');
    const orderId = params.get('orderId');
    const amount = params.get('amount');
    if (!paymentKey || !orderId || !amount) {
      setStatus('error');
      setMessage('결제 정보가 누락되었습니다');
      return;
    }
    if (confirmedRef.current) return; // StrictMode 중복 호출 방지 (서버도 멱등)
    confirmedRef.current = true;

    api.billing
      .confirm({ payment_key: paymentKey, order_id: orderId, amount_krw: Number(amount) })
      .then((res) => {
        setBalance(res.balance_krw);
        setStatus('done');
      })
      .catch((e: Error) => {
        setStatus('error');
        setMessage(e.message);
      });
  }, [params]);

  return (
    <div className="max-w-screen-md mx-auto px-6 py-16 text-center">
      {status === 'confirming' && (
        <p className="text-sm text-[#8B95A1] dark:text-[#6B7280]">결제 승인 확인 중…</p>
      )}

      {status === 'done' && (
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-10">
          <div className="w-12 h-12 mx-auto mb-4 flex items-center justify-center rounded-full bg-[#3182F6]/10 text-[#3182F6]">
            ✓
          </div>
          <h1 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">충전 완료</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mb-6">
            현재 크레딧 잔액{' '}
            <span className="font-semibold text-[#3182F6]">{balance?.toLocaleString()}원</span>
          </p>
          <Link
            href="/manage"
            className="inline-block px-6 py-3 bg-[#3182F6] text-white text-sm font-medium rounded-xl hover:bg-[#1B6EEB] transition-colors"
          >
            광고 매니지먼트로 이동
          </Link>
        </div>
      )}

      {status === 'error' && (
        <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-10">
          <h1 className="text-xl font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">승인 실패</h1>
          <p className="text-sm text-red-500 mb-6">{message}</p>
          <Link
            href="/payment"
            className="inline-block px-6 py-3 border border-[#E5E8EB] dark:border-[#2D3748] text-sm font-medium rounded-xl text-[#191F28] dark:text-[#F2F4F6]"
          >
            다시 시도
          </Link>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return (
    <AppLayout>
      <Suspense fallback={null}>
        <SuccessContent />
      </Suspense>
    </AppLayout>
  );
}
