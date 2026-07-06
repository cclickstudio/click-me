'use client';

// 채팅 안 시뮬레이션 결과 요약 위젯 — simulation_id로 KPI를 조회해 4대 지표를 보여준다.
// 별도 메시지로 DB에 영속화되므로 새로고침해도 복원된다(SimFormWidget 상태에 의존하지 않음).
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import type { SimAggregate, SimPersonaReaction } from '@/lib/types';

const cardCls =
  'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-4';

const pct1 = (n: number | null | undefined) => (n == null ? '—' : `${(n * 100).toFixed(0)}%`);
const sc = (n: number | null | undefined) => (n == null ? '—' : n.toFixed(2));

const REJECTION_LABEL: Record<string, string> = {
  irrelevant: '무관함',
  offensive: '불쾌함',
  overpriced: '비쌈',
  overpromise: '과장',
  distrust: '불신',
  ad_fatigue: '광고 피로',
  other: '기타',
};

// KOBACO(2019 MCR) 참고치(A-2) — aggregate.payload에 조회 결과가 실려온다(없으면 카드 생략).
type KobacoRef = {
  declared_category: string;
  kobaco_category: string;
  purchase_intent_pct: number | null;
  tv_ad_influence_pct: number | null;
};

export default function SimResultWidget({ simulationId }: { simulationId: string }) {
  const router = useRouter();
  const [agg, setAgg] = useState<SimAggregate | null>(null);
  const [reactions, setReactions] = useState<SimPersonaReaction[]>([]);
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
        if (cancelled) return;
        setAgg(r.aggregate ?? null);
        setReactions(r.reactions ?? []);
      } catch {
        if (!cancelled) setErr(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [simulationId]);

  // 구매의도 1~5 분포(F7) — QA 통과분 우선, 없으면 전체.
  const passed = reactions.filter(r => r.qa_passed);
  const purchaseDist = (() => {
    const counts = [0, 0, 0, 0, 0];
    let total = 0;
    for (const r of passed.length ? passed : reactions) {
      const pi = Math.round(r.purchase_intent);
      if (pi >= 1 && pi <= 5) {
        counts[pi - 1] += 1;
        total += 1;
      }
    }
    return { counts, total };
  })();
  // 거부 사유 분해(F8).
  const rejectionDist = (() => {
    const source = passed.length ? passed : reactions;
    const counts = new Map<string, number>();
    let total = 0;
    for (const r of source) {
      if (!r.rejected) continue;
      const tag = r.rejection_reason_tag ?? 'other';
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
      total += 1;
    }
    return { total, entries: [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3) };
  })();

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
              {agg && (
                <p className="text-[9px] text-[#B0B8C1]">
                  95% CI {pct1(agg.ci_low)}~{pct1(agg.ci_high)}
                </p>
              )}
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

          {/* 구매의도 분포 — 평균 단정 방지, 1~5점 분포 미니 막대 */}
          {purchaseDist.total > 0 && (
            <div className="mt-2 space-y-1">
              <p className="text-[10px] text-[#8B95A1]">구매의도 분포</p>
              {[5, 4, 3, 2, 1].map(score => {
                const c = purchaseDist.counts[score - 1];
                const ratio = purchaseDist.total ? (c / purchaseDist.total) * 100 : 0;
                return (
                  <div key={score} className="flex items-center gap-1.5 text-[10px]">
                    <span className="w-5 shrink-0 text-right text-[#8B95A1]">{score}점</span>
                    <div className="flex-1 h-2 rounded bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden">
                      <div
                        className="h-full rounded bg-[#3182F6] dark:bg-[#5B9DF9]"
                        style={{ width: `${ratio}%` }}
                      />
                    </div>
                    <span className="w-8 shrink-0 text-right text-[#B0B8C1]">{c}명</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* 거부 사유 분해 — 상위 3개만(좁은 채팅 폭 고려) */}
          {rejectionDist.total > 0 && (
            <div className="mt-2 space-y-1">
              <p className="text-[10px] text-[#8B95A1]">거부 사유(상위)</p>
              {rejectionDist.entries.map(([tag, c]) => {
                const ratio = rejectionDist.total ? (c / rejectionDist.total) * 100 : 0;
                return (
                  <div key={tag} className="flex items-center gap-1.5 text-[10px]">
                    <span className="w-14 shrink-0 text-right text-[#8B95A1]">
                      {REJECTION_LABEL[tag] ?? tag}
                    </span>
                    <div className="flex-1 h-2 rounded bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden">
                      <div
                        className="h-full rounded bg-[#F74D4D] dark:bg-[#F87171]"
                        style={{ width: `${ratio}%` }}
                      />
                    </div>
                    <span className="w-8 shrink-0 text-right text-[#B0B8C1]">{c}명</span>
                  </div>
                );
              })}
            </div>
          )}

          {(() => {
            const kobaco = agg?.payload?.kobaco_reference as KobacoRef | undefined;
            if (!kobaco) return null;
            return (
              <p className="mt-2 text-[11px] text-[#8B95A1] dark:text-[#6B7280]">
                KOBACO 참고({kobaco.kobaco_category}):{' '}
                {kobaco.purchase_intent_pct != null &&
                  `구매의향 ${pct1(kobaco.purchase_intent_pct)}`}
                {kobaco.purchase_intent_pct != null && kobaco.tv_ad_influence_pct != null && ' · '}
                {kobaco.tv_ad_influence_pct != null &&
                  `TV광고영향력 ${pct1(kobaco.tv_ad_influence_pct)}`}
                {' '}(척도 다름, 참고용)
              </p>
            );
          })()}
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
