'use client';

import { useEffect, useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api, type BeforeAfterItem } from '@/lib/api';

const VERDICT: Record<BeforeAfterItem['verdict'], { label: string; cls: string }> = {
  aligned: { label: '예측대로', cls: 'bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:text-[#7BB4F5]' },
  overperformed: {
    label: '예측보다 좋음',
    cls: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300',
  },
  underperformed: {
    label: '예측보다 약함',
    cls: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300',
  },
  unknown: { label: '판단 보류', cls: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300' },
};

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[11px] text-[#8B95A1]">{label}</p>
      <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">{value}</p>
      {hint && <p className="text-[10px] text-[#B0B8C1]">{hint}</p>}
    </div>
  );
}

function BeforeAfterCard({ item }: { item: BeforeAfterItem }) {
  const v = VERDICT[item.verdict];
  const p = item.prediction;
  const a = item.actual;
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] truncate">{item.name}</p>
        <span className={`text-[11px] font-semibold px-2 py-1 rounded-lg ${v.cls}`}>{v.label}</span>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {/* 집행 전 — 시뮬 예측 */}
        <div className="rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] p-3">
          <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-2">
            집행 전 · 시뮬 예측{' '}
            <span className="text-[10px] font-normal text-[#B0B8C1]">
              ({p ? (p.source === 'sim' ? '실 시뮬' : '예측(목)') : '미연결'})
            </span>
          </p>
          {p ? (
            <div className="grid grid-cols-2 gap-2.5">
              <Metric label="종합 적합도" value={`${p.objective_fit_score ?? '-'}점 ${p.grade ?? ''}`} />
              <Metric label="클릭 의향률" value={`${(p.click_intent_rate * 100).toFixed(0)}%`} />
              <Metric label="구매의도" value={`${p.purchase_intent.toFixed(1)}/5`} />
              <Metric label="신뢰도" value={`${p.trust_avg.toFixed(1)}/5`} />
            </div>
          ) : (
            <p className="text-xs text-[#B0B8C1] py-4 text-center">
              시뮬 연결 대기 — 이 광고로 시뮬을 돌리면 예측이 채워집니다
            </p>
          )}
        </div>
        {/* 집행 후 — 실측 */}
        <div className="rounded-xl bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] p-3">
          <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-2">
            집행 후 · 실측 <span className="text-[10px] font-normal text-[#3182F6]">(실 Meta)</span>
          </p>
          <div className="grid grid-cols-2 gap-2.5">
            <Metric label="CTR(클릭률)" value={`${(a.ctr * 100).toFixed(2)}%`} />
            <Metric label="지출" value={`₩${a.spend_krw.toLocaleString()}`} />
            <Metric
              label="전환율(CVR)"
              value={a.cvr != null ? `${(a.cvr * 100).toFixed(1)}%` : '추적 전'}
              hint={a.cvr == null ? '전환 추적 필요' : undefined}
            />
            <Metric
              label="ROAS"
              value={a.roas != null ? `${a.roas.toFixed(1)}x` : '추적 전'}
              hint={a.roas == null ? '전환가치 필요' : undefined}
            />
          </div>
        </div>
      </div>
      <p className="mt-3 text-[12px] text-[#8B95A1]">{item.rationale}</p>
    </div>
  );
}

export default function Page() {
  const [items, setItems] = useState<BeforeAfterItem[] | null>(null);
  const [baError, setBaError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.management
      .beforeAfter()
      .then((r) => {
        if (!alive) return;
        setItems(r.items);
        setRateLimited(r.rate_limited ?? null);
      })
      .catch((e) => {
        if (alive) {
          setItems([]);
          setBaError(e instanceof Error ? e.message : '불러오기 실패');
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">성과 비교</h1>
          <p className="text-sm text-[#8B95A1] mt-1">
            집행 전(시뮬 예측) ↔ 집행 후(실측) · 예측은 상대 지표, 실측은 실 Meta 절대값(환산 없이 방향성 비교)
          </p>
        </div>

        {/* 전/후 비교 — 주 화면 */}
        {items === null && <p className="text-sm text-[#8B95A1] py-10 text-center">불러오는 중…</p>}
        {items !== null && items.length > 0 && (
          <div className="space-y-4">
            {items.map((it) => (
              <BeforeAfterCard key={it.campaign_id} item={it} />
            ))}
          </div>
        )}
        {items !== null && items.length === 0 && (
          <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-8 text-center">
            {rateLimited ? (
              <>
                <p className="text-sm text-amber-700 dark:text-amber-300">{rateLimited}</p>
                <p className="text-xs text-[#B0B8C1] mt-1">
                  Meta 요청 한도에 일시적으로 걸렸습니다. 잠시 후 새로고침하면 실측이 표시됩니다.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF]">
                  아직 비교할 캠페인이 없습니다.
                </p>
                <p className="text-xs text-[#B0B8C1] mt-1">
                  캠페인을 게재하면 집행 후(실측)가 채워지고, 그 광고로 시뮬을 돌리면 집행 전(예측)이
                  나란히 표시됩니다.
                  {baError ? ' (DB 마이그레이션 필요: alembic upgrade head)' : ''}
                </p>
              </>
            )}
          </div>
        )}

        <p className="mt-6 text-[11px] text-[#B0B8C1]">
          예측=시뮬 상대 지표(클릭의향률·구매의도·적합도) · 실측=실 Meta 절대값(CTR·CVR·ROAS) ·
          스케일이 달라 환산 없이 방향성만 비교 · CVR/ROAS는 전환 추적 설정 시 표시
        </p>
      </div>
    </AppLayout>
  );
}
