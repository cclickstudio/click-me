'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

/** 크레딧 잔액 + 충전 버튼 — 잔액이 곧 광고 집행 한도가 된다. */
export default function CreditBalance() {
  const [balance, setBalance] = useState<number | null>(null);

  useEffect(() => {
    api.billing
      .balance()
      .then((res) => setBalance(res.balance_krw))
      .catch(() => setBalance(null)); // 백엔드 미기동 시 조용히 비표시
  }, []);

  return (
    <div className="flex items-center gap-3">
      <div className="text-right">
        <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">크레딧 잔액</p>
        <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">
          {balance === null ? '-' : `${balance.toLocaleString()}원`}
        </p>
      </div>
      <Link
        href="/payment"
        className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] transition-colors"
      >
        크레딧 충전
      </Link>
    </div>
  );
}
