'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { OrganicCard } from '@/components/manage/compare/OrganicCard';
import { PaidCard } from '@/components/manage/compare/PaidCard';
import { LiftPanel } from '@/components/manage/compare/LiftPanel';
import { LiftBoard } from '@/components/manage/compare/LiftBoard';
import { LiftDetailChart } from '@/components/manage/compare/LiftDetailChart';
import type { BoardRow, CompareResponse, CompareTab } from '@/components/manage/compare/types';

export default function Page() {
  const [tab, setTab] = useState<CompareTab>('A');
  const [single, setSingle] = useState<CompareResponse | null>(null);
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    setError(null);
    Promise.all([api.management.compare('ig_demo_1', 'camp_demo_1'), api.management.compareBoard()])
      .then(([a, b]) => {
        if (!alive) return;
        setSingle(a);
        setRows(b.rows);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : '불러오기 실패'))
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">게시물 성과 비교</h1>
            <p className="text-sm text-[#8B95A1] mt-1">
              오가닉 vs 광고 집행 · 증분 리프트 검증 (Mock 기반 데모)
            </p>
          </div>
          <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-sm">
            <button
              onClick={() => setTab('A')}
              className={`px-3 py-1.5 ${tab === 'A' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
            >
              A 나란히 비교
            </button>
            <button
              onClick={() => setTab('B')}
              className={`px-3 py-1.5 ${tab === 'B' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}
            >
              B 리프트 테이블
            </button>
          </div>
        </div>

        {busy && <p className="text-sm text-[#8B95A1] py-20 text-center">불러오는 중…</p>}
        {error && (
          <p className="text-sm text-red-500 py-20 text-center" role="alert">
            {error}
          </p>
        )}

        {!busy && !error && tab === 'A' && single && (
          <>
            <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-5 py-4 mb-4">
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">{single.title}</p>
              <p className="text-xs text-[#8B95A1] mt-1">
                동일 크리에이티브가 오가닉/광고 양쪽에 사용됨 · 1:1 비교
              </p>
            </div>
            <div className="flex flex-col lg:flex-row gap-4 items-stretch">
              <OrganicCard insights={single.lift.organic} />
              <PaidCard insights={single.lift.paid} />
              <LiftPanel lift={single.lift} />
            </div>
          </>
        )}

        {!busy && !error && tab === 'B' && rows.length > 0 && (
          <div className="space-y-4">
            <LiftBoard rows={rows} selected={selected} onSelect={setSelected} />
            <LiftDetailChart row={rows[selected]} />
          </div>
        )}

        <p className="mt-6 text-[11px] text-[#B0B8C1]">
          ⚠ Mock 기반 데모 · 오가닉/광고 도달은 중복 가능 → 단순 합산 금지 · 증분은 추정(분포) ·
          오가닉엔 CTR이 없어 참여율로 표기 · &quot;예측 CTR&quot; 등 실측 환산 없음 · 금액 KRW
        </p>
      </div>
    </AppLayout>
  );
}
