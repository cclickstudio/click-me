'use client';

// 크레딧 잔액 위젯 — 잔액(예산 한도) 표시. 충전은 COMPANY만(USER는 읽기 전용, ADMIN은 상위에서 미표시).

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from './AuthProvider';

/** 크레딧 잔액 + 충전 버튼 — 크레딧은 '예산 한도'(집행 상한)다. 실광고비는 Meta 선불에서 차감된다. */
export default function CreditBalance() {
  const { user } = useAuth();
  const [balance, setBalance] = useState<number | null>(null);
  const canCharge = user?.role === 'COMPANY'; // USER는 조직 공유 풀 읽기 전용, 충전은 COMPANY만

  useEffect(() => {
    api.billing
      .balance()
      .then((res) => setBalance(res.balance_krw))
      .catch(() => setBalance(null)); // 백엔드 미기동 시 조용히 비표시
  }, []);

  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-surface-1">
      <div className="min-w-0">
        <p className="text-[10px] text-ink-tertiary">크레딧 잔액 (예산 한도)</p>
        <p className="text-sm font-bold text-ink truncate">
          {balance === null ? '-' : `${balance.toLocaleString()}원`}
        </p>
      </div>
      {canCharge && (
        <Link
          href="/payment"
          className="shrink-0 px-2.5 py-1.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:bg-primary-hover transition-colors"
        >
          충전
        </Link>
      )}
    </div>
  );
}
