'use client';

// 채팅 안 시뮬레이션 결과 요약 위젯 — simulation_id로 KPI를 조회해 4대 지표를 보여준다.
// 별도 메시지로 DB에 영속화되므로 새로고침해도 복원된다(SimFormWidget 상태에 의존하지 않음).
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SimAggregate } from '@/lib/types';

const cardCls =
  'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-4';

const pct1 = (n: number | null | undefined) => (n == null ? '—' : `${(n * 100).toFixed(0)}%`);
const sc = (n: number | null | undefined) => (n == null ? '—' : n.toFixed(2));

export default function SimResultWidget({ simulationId }: { simulationId: string }) {
  const router = useRouter();
  const [agg, setAgg] = useState<SimAggregate | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.simulation.dbResult(simulationId);
        if (!cancelled) setAgg(r.aggregate ?? null);
      } catch {
        if (!cancelled) setErr(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [simulationId]);

  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">✅ 시뮬레이션 결과</p>
      {err ? (
        <p className="text-[12px] text-[#B0B8C1]">결과를 불러오지 못했어요.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
              <p className="text-[10px] text-[#8B95A1]">클릭 의향률</p>
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
                {agg ? pct1(agg.click_intent_rate) : '…'}
              </p>
            </div>
            <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
              <p className="text-[10px] text-[#8B95A1]">구매의도</p>
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
                {agg ? `${sc(agg.purchase_intent)}/5` : '…'}
              </p>
            </div>
            <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
              <p className="text-[10px] text-[#8B95A1]">신뢰도</p>
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
                {agg ? `${sc(agg.trust_avg)}/5` : '…'}
              </p>
            </div>
            <div className="rounded-lg bg-[#F9FAFB] dark:bg-[#252D3D] px-3 py-2">
              <p className="text-[10px] text-[#8B95A1]">거부율</p>
              <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">
                {agg ? pct1(agg.rejection_rate) : '…'}
              </p>
            </div>
          </div>
          <button
            onClick={() => router.push(`/simulation/${simulationId}`)}
            className="mt-3 w-full py-2 rounded-lg border border-[#3182F6]/30 text-[#3182F6] text-sm font-semibold hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors"
          >
            상세 보기 →
          </button>
        </>
      )}
    </div>
  );
}
