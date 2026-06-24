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
  const [copied, setCopied] = useState(false);

  // KPI 4종을 실무용 텍스트로 클립보드에 복사(P10).
  const copyKpis = async () => {
    if (!agg) return;
    const text = [
      '시뮬레이션 결과(클릭미)',
      `클릭 의향률: ${pct1(agg.click_intent_rate)}`,
      `구매의도: ${sc(agg.purchase_intent)}/5`,
      `신뢰도: ${sc(agg.trust_avg)}/5`,
      `거부율: ${pct1(agg.rejection_rate)}`,
    ].join('\n');
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      // 클립보드 API 불가(비보안 컨텍스트·iframe 등) — execCommand 폴백.
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand('copy');
        document.body.removeChild(ta);
      } catch {
        ok = false;
      }
    }
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }
  };

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
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">✅ 시뮬레이션 결과</p>
        {agg && !err && (
          <button
            onClick={copyKpis}
            title="KPI 복사"
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#8B95A1] hover:text-[#3182F6] transition-colors"
          >
            {copied ? (
              <>✓ 복사됨</>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                복사
              </>
            )}
          </button>
        )}
      </div>
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
