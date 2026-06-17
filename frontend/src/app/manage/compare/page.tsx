'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { LiftBoard } from '@/components/manage/compare/LiftBoard';
import { LiftDetailChart } from '@/components/manage/compare/LiftDetailChart';
import type { BoardRow } from '@/components/manage/compare/types';

export default function Page() {
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    setError(null);
    api.management
      .compareBoard()
      .then((b) => alive && setRows(b.rows))
      .catch((e) => alive && setError(e instanceof Error ? e.message : '불러오기 실패'))
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">게시물 성과 비교</h1>
          <p className="text-sm text-[#8B95A1] mt-1">
            오가닉→광고 증분 리프트 검증 보드 (Mock 기반 데모)
          </p>
        </div>

        {busy && <p className="text-sm text-[#8B95A1] py-20 text-center">불러오는 중…</p>}
        {error && (
          <p className="text-sm text-red-500 py-20 text-center" role="alert">
            {error}
          </p>
        )}

        {!busy && !error && rows.length > 0 && (
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
