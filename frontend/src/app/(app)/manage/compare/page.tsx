'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, type BeforeAfterItem, type CalibrationResponse } from '@/lib/api';

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

// 클릭 축 기준선 통과 배지 — 강함/약함(예측·실측 각자 기준, 환산 없음). null이면 판정 불가(—).
function StrongBadge({
  strong,
  strongLabel,
  weakLabel,
}: {
  strong: boolean | null | undefined;
  strongLabel: string;
  weakLabel: string;
}) {
  if (strong == null)
    return <span className="text-[10px] text-[#B0B8C1]">판정 불가</span>;
  return strong ? (
    <span className="text-[10px] font-semibold text-green-600 dark:text-green-400">
      ● {strongLabel}
    </span>
  ) : (
    <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400">
      ● {weakLabel}
    </span>
  );
}

function BeforeAfterCard({
  item,
  onRunSim,
  simLoading,
}: {
  item: BeforeAfterItem;
  onRunSim: (campaignId: string) => void;
  simLoading: string | null;
}) {
  const v = VERDICT[item.verdict];
  const p = item.prediction;
  const a = item.actual;
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5">
      <div className="flex items-center justify-between mb-4">
        <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] truncate">{item.name}</p>
        <span className={`text-[11px] font-semibold px-2 py-1 rounded-lg ${v.cls}`}>{v.label}</span>
      </div>

      {/* 핵심 방향성 — 클릭 의향률(예측) ⟷ CTR(실측). 각자 기준선 통과로만 비교(스케일 환산 금지). */}
      <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#252D3D] p-4 mb-3">
        <p className="text-[11px] text-[#8B95A1] mb-2.5">
          클릭 방향성 — 예측·실측을 각자 기준선으로 비교(환산 없이 방향만)
        </p>
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <p className="text-[11px] text-[#8B95A1]">클릭 의향률 · 예측</p>
            <p className="text-lg font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">
              {p ? `${(p.click_intent_rate * 100).toFixed(0)}%` : '—'}
            </p>
            <StrongBadge strong={item.pred_strong} strongLabel="강함 ≥20%" weakLabel="약함 <20%" />
          </div>
          <span className="text-xl text-[#8B95A1] shrink-0">⟷</span>
          <div className="flex-1 text-right">
            <p className="text-[11px] text-[#8B95A1]">
              CTR · 실측 <span className="text-[#3182F6]">(실 Meta)</span>
            </p>
            <p className="text-lg font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">
              {`${(a.ctr * 100).toFixed(2)}%`}
            </p>
            <StrongBadge strong={item.act_strong} strongLabel="양호 ≥1%" weakLabel="약함 <1%" />
          </div>
        </div>
      </div>

      {/* 구매 방향성 — 구매의도(예측, /5) ⟷ CVR(실측, %). 척도가 달라 직접 환산 아님 — 각자 기준선 통과로만 비교. */}
      <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#252D3D] p-4 mb-3">
        <p className="text-[11px] text-[#8B95A1] mb-2.5">
          구매의도와 CVR은 서로 환산하지 않고, 각자 기준선 통과 여부만 봅니다.
        </p>
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <p className="text-[11px] text-[#8B95A1]">구매의도 · 예측</p>
            <p className="text-lg font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">
              {p ? `${p.purchase_intent.toFixed(1)}/5` : '—'}
            </p>
            <StrongBadge strong={item.purchase_pred_strong} strongLabel="강함 ≥3.5" weakLabel="약함 <3.5" />
          </div>
          <span className="text-xl text-[#8B95A1] shrink-0">⟷</span>
          <div className="flex-1 text-right">
            <p className="text-[11px] text-[#8B95A1]">
              CVR · 실측 <span className="text-[#3182F6]">(실 Meta)</span>
            </p>
            <p className="text-lg font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">
              {a.cvr != null ? `${(a.cvr * 100).toFixed(1)}%` : '추적 전'}
            </p>
            <StrongBadge strong={item.purchase_act_strong} strongLabel="양호 ≥2%" weakLabel="약함 <2%" />
          </div>
        </div>
      </div>

      {/* 보조 — 예측 KPI(판정 외) ↔ 실측 KPI */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl bg-[#F9FAFB] dark:bg-[#252D3D] p-3">
          <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-2">
            집행 전 · 시뮬 예측{' '}
            <span className="text-[10px] font-normal text-[#B0B8C1]">
              ({p ? (p.source === 'sim' ? '실 시뮬' : '예측(목)') : '미연결'})
            </span>
          </p>
          {p ? (
            <div className="grid grid-cols-3 gap-2">
              <Metric label="구매의도" value={`${p.purchase_intent.toFixed(1)}/5`} />
              <Metric label="신뢰도" value={`${p.trust_avg.toFixed(1)}/5`} />
              <Metric label="거부율" value={`${(p.rejection_rate * 100).toFixed(0)}%`} />
            </div>
          ) : (
            <div className="py-3 text-center">
              <p className="text-xs text-[#B0B8C1] mb-2">
                시뮬 연결 대기 — 이 광고로 시뮬을 돌리면 예측이 채워집니다
              </p>
              <button
                onClick={() => onRunSim(item.campaign_id)}
                disabled={simLoading === item.campaign_id}
                className="px-3 py-1.5 rounded-lg bg-[#3182F6] hover:bg-[#1B64DA] disabled:opacity-60 text-white text-xs font-semibold transition-colors"
              >
                {simLoading === item.campaign_id ? '불러오는 중…' : '이 캠페인으로 시뮬 돌리기'}
              </button>
            </div>
          )}
        </div>
        <div className="rounded-xl bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] p-3">
          <p className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] mb-2">
            집행 후 · 실측 <span className="text-[10px] font-normal text-[#3182F6]">(실 Meta)</span>
          </p>
          <div className="grid grid-cols-3 gap-2">
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
      {item.interpretation && (
        <p className="mt-1 text-[12px] text-[#B0B8C1] dark:text-[#6B7280]">↳ {item.interpretation}</p>
      )}
      {!p && (
        <p className="mt-2 text-[11px] text-[#B0B8C1]">
          시뮬 미연결 — 예측 데이터 없음
        </p>
      )}
    </div>
  );
}

// 순위 일치율 → 색상(0.7+ 양호 / 0.5+ 보통 / 그 외 약함). null이면 회색.
function concordanceCls(v: number | null | undefined): string {
  if (v == null) return 'text-[#8B95A1]';
  if (v >= 0.7) return 'text-green-600 dark:text-green-400';
  if (v >= 0.5) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-500 dark:text-red-400';
}
const pct = (v: number | null | undefined) => (v == null ? '데이터 부족' : `${Math.round(v * 100)}%`);

function CalibrationCard({ calib }: { calib: CalibrationResponse }) {
  const s = calib.summary;
  const progress = Math.min((s.n / s.unlock_threshold) * 100, 100);
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5 mb-4 bg-[#F9FAFB] dark:bg-[#252D3D]">
      <div className="flex items-center justify-between mb-1">
        <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">캘리브레이션 앵커</p>
        <span
          className={`text-[11px] font-semibold px-2 py-1 rounded-lg ${
            s.unlocked
              ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300'
              : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300'
          }`}
        >
          {s.unlocked ? '✓ calibration 검토 가능' : `해금 ${s.n}/${s.unlock_threshold}`}
        </span>
      </div>
      <p className="text-xs text-[#8B95A1] mb-4">
        집행된 광고의 예측↔실측을 자동 수집해 시뮬 방향성을 검증합니다 (절대 환산 전 단계 · 순위
        일치율).
      </p>
      {s.n === 0 ? (
        <p className="text-xs text-[#B0B8C1] py-2">
          연결된(시뮬↔집행) 캠페인이 쌓이면 앵커가 자동 수집됩니다. 제너레이터→시뮬→집행으로 광고를
          돌려보세요.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div>
              <p className="text-[11px] text-[#8B95A1]">수집된 앵커</p>
              <p className="text-2xl font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">
                {s.n}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-[#8B95A1]">클릭 방향성 정합</p>
              <p className={`text-2xl font-extrabold tabular-nums ${concordanceCls(s.concordance_click)}`}>
                {pct(s.concordance_click)}
              </p>
              <p className="text-[10px] text-[#B0B8C1]">예측 클릭의향률 ↔ 실측 CTR</p>
            </div>
            <div>
              <p className="text-[11px] text-[#8B95A1]">구매 방향성 정합</p>
              <p
                className={`text-2xl font-extrabold tabular-nums ${concordanceCls(s.concordance_purchase)}`}
              >
                {pct(s.concordance_purchase)}
              </p>
              <p className="text-[10px] text-[#B0B8C1]">예측 구매의도 ↔ 실측 CVR</p>
            </div>
          </div>
          <div className="h-1.5 w-full rounded-full bg-[#E5E8EB] dark:bg-[#2D3748] overflow-hidden">
            <div
              className={`h-full ${s.unlocked ? 'bg-green-500' : 'bg-[#3182F6]'}`}
              style={{ width: `${progress}%` }}
            />
          </div>
          {!s.unlocked && (
            <p className="mt-2 text-[10px] text-[#B0B8C1]">
              ⚠ 표본 적음(N&lt;{s.unlock_threshold}) — 방향성 정합은 탐색적입니다. 앵커가 누적될수록
              신뢰도가 올라가고, {s.unlock_threshold}건부터 calibration(절대 환산) 검토가 열립니다.
            </p>
          )}
        </>
      )}
    </div>
  );
}

// Meta objective → 시뮬레이터 광고 목표 매핑
const _OBJECTIVE_MAP: Record<string, string> = {
  OUTCOME_AWARENESS: '관심 유도',
  OUTCOME_TRAFFIC: '클릭 유도',
  OUTCOME_ENGAGEMENT: '관심 유도',
  OUTCOME_LEADS: '가입·문의 유도',
  OUTCOME_APP_PROMOTION: '클릭 유도',
  OUTCOME_SALES: '구매 전환',
};

export default function Page() {
  const router = useRouter();
  const [items, setItems] = useState<BeforeAfterItem[] | null>(null);
  const [calib, setCalib] = useState<CalibrationResponse | null>(null);
  const [baError, setBaError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState<string | null>(null);
  const [simLoading, setSimLoading] = useState<string | null>(null); // 로딩 중인 campaign_id

  const handleRunSim = useCallback(async (campaignId: string) => {
    setSimLoading(campaignId);
    try {
      const t = await api.management.campaignTargeting(campaignId);
      const params = new URLSearchParams({ from_campaign: campaignId });
      if (t.campaign_name) params.set('from_name', t.campaign_name);
      if (t.objective) params.set('objective', _OBJECTIVE_MAP[t.objective] ?? '');
      if (t.age_min != null) params.set('age_min', String(t.age_min));
      if (t.age_max != null) params.set('age_max', String(t.age_max));
      if (t.gender) params.set('gender', t.gender);
      if (t.ad_headline) params.set('ad_title', t.ad_headline);
      if (t.ad_body) params.set('ad_content', t.ad_body);
      if (t.category_id) params.set('category_id', String(t.category_id));
      if (t.service_class) params.set('service_class', String(t.service_class));
      if (t.suggested_persona_count) params.set('persona_count', String(t.suggested_persona_count));
      // Meta 이미지는 fbcdn CORS 제한으로 직접 로드 불가 → 백엔드 프록시 URL 사용
      if (t.ad_image_url) {
        const proxyUrl = `${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/management/campaigns/${campaignId}/creative-image`;
        params.set('ad_image_url', proxyUrl);
      }
      router.push(`/simulation?${params.toString()}`);
    } catch {
      alert('타겟팅 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      setSimLoading(null);
    }
  }, [router]);

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
    api.management
      .calibrationAnchors()
      .then((r) => alive && setCalib(r))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  return (
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">성과 비교</h1>
          <p className="text-sm text-[#8B95A1] mt-1">
            집행 전(시뮬 예측) ↔ 집행 후(실측) · 예측은 상대 지표, 실측은 실 Meta 절대값(환산 없이 방향성 비교)
          </p>
        </div>

        {/* 베이스라인 앵커 — 예측↔실측 자동 수집 + 방향성 정합 */}
        {calib && <CalibrationCard calib={calib} />}

        {/* 전/후 비교 — 주 화면 */}
        {items === null && <p className="text-sm text-[#8B95A1] py-10 text-center">불러오는 중…</p>}
        {items !== null && items.length > 0 && (
          <div className="space-y-4">
            {items.map((it) => (
              <BeforeAfterCard
                key={it.campaign_id}
                item={it}
                onRunSim={handleRunSim}
                simLoading={simLoading}
              />
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
  );
}
