'use client';
// 성과 비교 — 시뮬 예측(집행 전)과 실제 성과(집행 후)를 캠페인별로 나란히 비교하는 화면

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, type BeforeAfterItem, type CalibrationResponse, type PredictionSnapshot, type ActualOutcome } from '@/lib/api';
import { formatKSTDate } from '@/lib/datetime';
import { goalFromObjective } from '@/lib/metaObjective';

const VERDICT: Record<
  BeforeAfterItem['verdict'],
  { label: string; cls: string; accent: string }
> = {
  aligned: {
    label: '예측대로',
    cls: 'bg-[#EBF3FF] text-primary dark:bg-[#1E3A5F] dark:text-[#7BB4F5]',
    accent: 'border-l-[#3182F6]',
  },
  overperformed: {
    label: '예측보다 좋음',
    cls: 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-300',
    accent: 'border-l-[#22C55E]',
  },
  underperformed: {
    label: '예측보다 약함',
    cls: 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300',
    accent: 'border-l-[#F59E0B]',
  },
  unknown: {
    label: '비교 대기',
    cls: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300',
    accent: 'border-l-[#D1D6DB] dark:border-l-[#4B5563]',
  },
};

// 바 색 — 다른 탭과 동일 문법: 값 막대는 파랑 패밀리(퍼널의 #3182F6/#5B9DF9 페어링 재사용),
// 판정(강함/약함)은 배지·캡션 텍스트가 담당. 좌우 정체는 위치+라벨로 명시(색 단독 아님).
const ACT_FILL = '#3182F6'; // 실측(Meta) — 앱 전반의 실측 파랑
const PRED_FILL = '#5B9DF9'; // 시뮬 예측 — 같은 패밀리 연파랑

const VERDICT_ORDER: BeforeAfterItem['verdict'][] = [
  'overperformed',
  'underperformed',
  'aligned',
  'unknown',
];

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[11px] text-ink-tertiary">{label}</p>
      <p className="text-sm font-bold text-ink tabular-nums">{value}</p>
      {hint && <p className="text-[10px] text-ink-muted">{hint}</p>}
    </div>
  );
}

// 기준 통과 여부 → 캡션 텍스트/색 (예측·실측 각자 기준, 환산 없음)
const capText = (
  s: boolean | null | undefined,
  strong: string,
  weak: string,
  na: string,
): string => (s === true ? strong : s === false ? weak : na);
const capCls = (s: boolean | null | undefined): string =>
  s === true
    ? 'text-green-600 dark:text-green-400'
    : s === false
      ? 'text-amber-600 dark:text-amber-400'
      : 'text-ink-muted';

// 미러 바 — 중앙에서 좌(예측)/우(실측)로 자라는 막대 + 기준선 마커. 좌우는 각자 축(환산 금지).
function MirrorBar({
  num,
  threshold,
  max,
  side,
}: {
  num: number | null;
  threshold: number;
  max?: number;
  side: 'left' | 'right';
}) {
  if (num == null) {
    // 데이터 없음(시뮬 미연결·집계 전) — 죽은 회색 바 대신 점선 트랙으로 '비어 있음'을 표현
    return (
      <div className="h-4 flex-1 rounded-full border-2 border-dashed border-[#D1D6DB] dark:border-[#4B5563]" />
    );
  }
  const scale = max ?? Math.max(threshold * 2, num * 1.15, 0.0001);
  const widthPct = Math.max(Math.min((num / scale) * 100, 100), 1.5);
  const tickPct = Math.min((threshold / scale) * 100, 100);
  const fill = side === 'left' ? PRED_FILL : ACT_FILL;
  return (
    <div className="relative h-4 flex-1 rounded-full bg-surface-1">
      <div
        className={`absolute inset-y-0 ${side === 'left' ? 'right-0 rounded-l-full' : 'left-0 rounded-r-full'}`}
        style={{ width: `${widthPct}%`, background: fill }}
      />
      <div
        className="absolute top-1/2 h-[170%] w-[2px] -translate-y-1/2 rounded bg-[#4E5968] dark:bg-[#9CA3AF]"
        style={side === 'left' ? { right: `${tickPct}%` } : { left: `${tickPct}%` }}
        title="기준선"
      />
    </div>
  );
}

type MirrorSide = {
  label: string;
  value: string;
  num: number | null;
  threshold: number;
  max?: number;
  strong: boolean | null | undefined;
  caption: string;
};

// 미러(나비형) 축 행 — 큰 숫자 + 대칭 바. 대칭은 시선 유도용이며 좌우 스케일 비교가 아니다.
function MirrorRow({
  axis,
  pred,
  act,
  onRun,
  running,
}: {
  axis: string;
  pred: MirrorSide;
  act: MirrorSide;
  onRun?: () => void; // 예측 없음(시뮬 미연결)일 때 인라인 실행 버튼
  running?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="w-32 shrink-0 text-right">
        <p className="text-[10px] text-ink-tertiary">{pred.label}</p>
        <p className="text-2xl font-extrabold leading-tight tabular-nums text-ink">
          {pred.value}
        </p>
        {pred.num == null && onRun ? (
          <button
            onClick={onRun}
            disabled={running}
            className="mt-0.5 text-[10px] font-bold text-primary hover:underline disabled:opacity-60"
          >
            {running ? '불러오는 중…' : '시뮬 돌리기 →'}
          </button>
        ) : (
          <p className={`text-[10px] font-bold ${capCls(pred.strong)}`}>{pred.caption}</p>
        )}
      </div>
      <MirrorBar side="left" num={pred.num} threshold={pred.threshold} max={pred.max} />
      <span className="w-12 shrink-0 text-center text-[11px] font-bold text-ink-secondary">
        {axis}
      </span>
      <MirrorBar side="right" num={act.num} threshold={act.threshold} max={act.max} />
      <div className="w-32 shrink-0">
        <p className="text-[10px] text-ink-tertiary">{act.label}</p>
        <p className="text-2xl font-extrabold leading-tight tabular-nums text-ink">
          {act.value}
        </p>
        <p className={`text-[10px] font-bold ${capCls(act.strong)}`}>{act.caption}</p>
      </div>
    </div>
  );
}

// 판정 근거 — 클릭/구매 축 기준선 통과 여부를 구조적으로 설명
function VerdictReason({ item, p, a }: { item: BeforeAfterItem; p: PredictionSnapshot | null; a: ActualOutcome }) {
  const cirVal = p ? `${(p.click_intent_rate * 100).toFixed(0)}%` : '—';
  const ctrVal = `${(a.ctr * 100).toFixed(2)}%`;
  const piVal = p ? `${p.purchase_intent.toFixed(1)}/5` : '—';
  const cvrVal = a.cvr != null ? `${(a.cvr * 100).toFixed(1)}%` : '추적 전';

  const clickPredIcon = item.pred_strong === true ? '✅' : item.pred_strong === false ? '❌' : '—';
  const clickActIcon = item.act_strong === true ? '✅' : item.act_strong === false ? '❌' : '—';
  const purchPredIcon = item.purchase_pred_strong === true ? '✅' : item.purchase_pred_strong === false ? '❌' : '—';
  const purchActIcon = item.purchase_act_strong === true ? '✅' : item.purchase_act_strong === false ? '❌' : '—';

  const verdictDesc: Record<BeforeAfterItem['verdict'], string> = {
    overperformed: '예측보다 실측이 좋아요 — 집행 후 성과가 시뮬 예측을 넘었어요.',
    underperformed: '예측보다 실측이 약해요 — 시뮬 예측에 비해 실제 성과가 낮아요.',
    aligned: '예측과 실측의 방향이 같아요 — 시뮬 예측대로 결과가 나왔어요.',
    unknown: '아직 비교하기 어려워요 — 데이터가 부족하거나 클릭·구매 방향이 서로 달라요.',
  };

  return (
    <div className="rounded-xl border border-line bg-surface-1 p-4 space-y-3">
      <p className="text-xs font-semibold text-ink-secondary">왜 이렇게 판단했나요</p>

      {/* 클릭 축 */}
      <div className="space-y-1">
        <p className="text-[11px] font-semibold text-ink">클릭 축</p>
        <div className="flex gap-4 text-[11px] text-ink-secondary">
          <span>
            {clickPredIcon} 클릭 의향률(예측) <strong>{cirVal}</strong>
            {item.pred_strong != null && (
              <span className="ml-1 text-ink-muted">
                (기준 20% {item.pred_strong ? '통과 → 강함' : '미달 → 약함'})
              </span>
            )}
          </span>
          <span className="text-ink-muted">⟷</span>
          <span>
            {clickActIcon} CTR(실측) <strong>{ctrVal}</strong>
            {item.act_strong != null && (
              <span className="ml-1 text-ink-muted">
                (기준 1% {item.act_strong ? '통과 → 양호' : '미달 → 약함'})
              </span>
            )}
          </span>
        </div>
      </div>

      {/* 구매 축 */}
      <div className="space-y-1">
        <p className="text-[11px] font-semibold text-ink">구매 축</p>
        <div className="flex gap-4 text-[11px] text-ink-secondary">
          <span>
            {purchPredIcon} 구매의도(예측) <strong>{piVal}</strong>
            {item.purchase_pred_strong != null && (
              <span className="ml-1 text-ink-muted">
                (기준 3.5/5 {item.purchase_pred_strong ? '통과 → 강함' : '미달 → 약함'})
              </span>
            )}
          </span>
          <span className="text-ink-muted">⟷</span>
          <span>
            {purchActIcon} CVR(실측) <strong>{cvrVal}</strong>
            {item.purchase_act_strong != null && (
              <span className="ml-1 text-ink-muted">
                (기준 2% {item.purchase_act_strong ? '통과 → 양호' : '미달 → 약함'})
              </span>
            )}
          </span>
        </div>
      </div>

      <p className="text-[11px] text-primary font-medium border-t border-line pt-2">
        → {verdictDesc[item.verdict]}
      </p>
      {item.rationale && (
        <p className="text-[11px] text-ink-tertiary">{item.rationale}</p>
      )}
      {item.interpretation && (
        <p className="text-[11px] text-ink-muted">↳ {item.interpretation}</p>
      )}
    </div>
  );
}

// 집행 전 시뮬 전체 상세 패널
function SimDetail({ p }: { p: PredictionSnapshot }) {
  const date = formatKSTDate(p.as_of);
  return (
    <div className="rounded-xl bg-surface-1 p-3">
      <p className="text-xs font-semibold text-ink-secondary mb-2.5">
        집행 전 · 시뮬 전체 결과{' '}
        <span className="text-[10px] font-normal text-ink-muted">({p.source === 'sim' ? '실 시뮬' : '예측(목)'} · {date})</span>
      </p>
      <div className="grid grid-cols-4 gap-3">
        <Metric
          label="클릭 의향률"
          value={`${(p.click_intent_rate * 100).toFixed(0)}%`}
          hint="기준 ≥20% 강함"
        />
        <Metric
          label="구매의도"
          value={`${p.purchase_intent.toFixed(1)}/5`}
          hint="기준 ≥3.5 강함"
        />
        <Metric label="신뢰도" value={`${p.trust_avg.toFixed(1)}/5`} />
        <Metric
          label="거부율"
          value={`${(p.rejection_rate * 100).toFixed(0)}%`}
          hint="낮을수록 좋음"
        />
      </div>
    </div>
  );
}

// 집행 후 실측 전체 상세 패널
function ActDetail({ a }: { a: ActualOutcome }) {
  return (
    <div className="rounded-xl bg-card border border-line p-3">
      <p className="text-xs font-semibold text-ink-secondary mb-2.5">
        집행 후 · 실측 전체{' '}
        <span className="text-[10px] font-normal text-primary">(Meta)</span>
      </p>
      <div className="grid grid-cols-4 gap-3">
        <Metric label="노출수" value={a.impressions.toLocaleString()} />
        <Metric label="도달수(Reach)" value={a.reach.toLocaleString()} />
        <Metric label="지출(Spend)" value={`₩${a.spend_krw.toLocaleString()}`} />
        <Metric label="CTR(클릭률)" value={`${(a.ctr * 100).toFixed(2)}%`} hint="기준 ≥1% 양호" />
        <Metric label="CPC" value={`₩${a.cpc_krw.toLocaleString()}`} />
        <Metric label="CPM" value={`₩${a.cpm_krw.toLocaleString()}`} />
        <Metric
          label="CVR(전환율)"
          value={a.cvr != null ? `${(a.cvr * 100).toFixed(1)}%` : '집계 전'}
          hint={a.cvr != null ? '기준 ≥2% 양호 · 전환=구매·리드·가입 등' : '전환(구매·리드·가입 등)이 잡히면 표시돼요'}
        />
        <Metric
          label="ROAS"
          value={a.roas != null ? `${a.roas.toFixed(1)}x` : '집계 전'}
          hint={a.roas == null ? '구매 금액(전환가치)이 잡히면 계산돼요' : undefined}
        />
      </div>
      {a.conversions != null && (
        <p className="mt-2 text-[11px] text-ink-tertiary">전환수: {a.conversions.toLocaleString()}건</p>
      )}
    </div>
  );
}

// 판정별 다음 행동 — 대시보드는 표시가 아니라 결정을 돕는 화면이어야 한다.
function ActionRow({
  item,
  onRunSim,
  simLoading,
}: {
  item: BeforeAfterItem;
  onRunSim: (campaignId: string) => void;
  simLoading: string | null;
}) {
  const running = simLoading === item.campaign_id;
  const rerunBtn = (
    <button
      onClick={() => onRunSim(item.campaign_id)}
      disabled={running}
      className="px-3 py-1.5 rounded-lg border border-line text-xs font-semibold text-ink-secondary hover:border-primary hover:text-primary disabled:opacity-60 transition-colors"
    >
      {running ? '불러오는 중…' : item.prediction ? '시뮬 다시 돌리기' : '이 캠페인으로 시뮬 돌리기'}
    </button>
  );
  return (
    <div className="flex items-center gap-2 pt-1">
      {item.verdict === 'overperformed' && (
        <Link
          href="/manage/budget"
          className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-semibold transition-colors"
        >
          예산 늘리기 검토 →
        </Link>
      )}
      {item.verdict === 'underperformed' && (
        <Link
          href="/generator"
          className="px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-semibold transition-colors"
        >
          개선 시안 만들기 →
        </Link>
      )}
      {rerunBtn}
    </div>
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
  const [open, setOpen] = useState(false);
  const v = VERDICT[item.verdict];
  const p = item.prediction;
  const a = item.actual;
  const running = simLoading === item.campaign_id;
  return (
    <div
      className={`rounded-2xl border border-l-4 border-line ${v.accent} bg-card`}
    >
      {/* 헤더(토글) — 이름·판정 배지·지출 */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-5 pt-4 pb-1 text-left"
      >
        <p className="text-base font-bold text-ink truncate flex-1">
          {item.name}
        </p>
        <span className={`text-xs font-bold px-2.5 py-1 rounded-lg shrink-0 ${v.cls}`}>
          {v.label}
        </span>
        <span className="text-xs text-ink-tertiary tabular-nums shrink-0">
          ₩{a.spend_krw.toLocaleString()}
        </span>
        <span
          className={`text-ink-muted text-xs shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        >
          ▼
        </span>
      </button>

      {/* 미러 축 2행 — 좌=시뮬 예측 / 우=실측(Meta). 좌우는 각자 축·기준선(환산 없음). */}
      <div className="px-5 pb-4">
        <div className="flex items-center justify-between px-0.5 text-[10px] font-semibold text-ink-muted">
          <span>◀ 시뮬 예측</span>
          <span>
            실측 <span className="text-primary">(Meta)</span> ▶
          </span>
        </div>
        <MirrorRow
          axis="클릭"
          pred={{
            label: '클릭 의향률',
            value: p ? `${(p.click_intent_rate * 100).toFixed(0)}%` : '—',
            num: p ? p.click_intent_rate : null,
            threshold: 0.2,
            max: 0.4,
            strong: item.pred_strong,
            caption: capText(item.pred_strong, '강함 ≥20%', '약함 <20%', '시뮬 미연결'),
          }}
          act={{
            label: 'CTR(클릭률)',
            value: `${(a.ctr * 100).toFixed(2)}%`,
            num: a.ctr,
            threshold: 0.01,
            strong: item.act_strong,
            caption: capText(item.act_strong, '양호 ≥1%', '약함 <1%', '판정 대기'),
          }}
          onRun={() => onRunSim(item.campaign_id)}
          running={running}
        />
        <div className="border-t border-line" />
        <MirrorRow
          axis="구매"
          pred={{
            label: '구매의도',
            value: p ? `${p.purchase_intent.toFixed(1)}/5` : '—',
            num: p ? p.purchase_intent : null,
            threshold: 3.5,
            max: 5,
            strong: item.purchase_pred_strong,
            caption: capText(item.purchase_pred_strong, '강함 ≥3.5', '약함 <3.5', '시뮬 미연결'),
          }}
          act={{
            label: 'CVR(전환율)',
            value: a.cvr != null ? `${(a.cvr * 100).toFixed(1)}%` : '집계 전',
            num: a.cvr ?? null,
            threshold: 0.02,
            strong: item.purchase_act_strong,
            caption: capText(
              item.purchase_act_strong,
              '양호 ≥2%',
              '약함 <2%',
              a.cvr == null ? '전환 잡히면 표시' : '판정 대기',
            ),
          }}
          onRun={() => onRunSim(item.campaign_id)}
          running={running}
        />
      </div>

      {/* 펼침 — 판정 근거 + 전/후 전체 상세 + 다음 행동 */}
      {open && (
        <div className="px-5 pb-5 pt-4 space-y-3 border-t border-line">
          <VerdictReason item={item} p={p} a={a} />
          {p && <SimDetail p={p} />}
          <ActDetail a={a} />
          <ActionRow item={item} onRunSim={onRunSim} simLoading={simLoading} />
        </div>
      )}
    </div>
  );
}

// 예측 적중률 → 색상(0.7+ 양호 / 0.5+ 보통 / 그 외 약함). null이면 회색.
function concordanceCls(v: number | null | undefined): string {
  if (v == null) return 'text-ink-tertiary';
  if (v >= 0.7) return 'text-green-600 dark:text-green-400';
  if (v >= 0.5) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-500 dark:text-red-400';
}
const pct = (v: number | null | undefined) => (v == null ? '데이터 부족' : `${Math.round(v * 100)}%`);

// 예측 정확도 검증(캘리브레이션) — 기본은 접힌 한 줄, 펼치면 상세.
function CalibrationCard({ calib }: { calib: CalibrationResponse }) {
  const [open, setOpen] = useState(false);
  const s = calib.summary;
  const progress = Math.min((s.n / s.unlock_threshold) * 100, 100);
  return (
    <div className="rounded-2xl border border-line mb-4 bg-surface-1">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-3 text-left"
      >
        <p className="text-xs font-semibold text-ink-secondary">
          예측 정확도 검증
          <span className="ml-2 font-normal text-ink-tertiary">
            {s.unlocked
              ? '정밀 검증 준비 완료'
              : `비교 데이터 ${s.n}/${s.unlock_threshold}건 수집 중`}
          </span>
        </p>
        <span className={`text-ink-muted text-xs transition-transform ${open ? 'rotate-180' : ''}`}>▼</span>
      </button>
      {open && (
        <div className="px-5 pb-4">
          <p className="text-xs text-ink-tertiary mb-4">
            광고를 집행할 때마다 예측과 실제 결과를 자동으로 모아, 시뮬 예측이 얼마나 맞는지
            확인해요.
          </p>
          {s.n === 0 ? (
            <p className="text-xs text-ink-muted py-2">
              시뮬과 연결된 캠페인이 쌓이면 자동으로 수집돼요. 제너레이터→시뮬→집행으로 광고를
              돌려보세요.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div>
                  <p className="text-[11px] text-ink-tertiary">모인 비교 데이터</p>
                  <p className="text-2xl font-extrabold text-ink tabular-nums">
                    {s.n}건
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-ink-tertiary">클릭 예측 적중률</p>
                  <p className={`text-2xl font-extrabold tabular-nums ${concordanceCls(s.concordance_click)}`}>
                    {pct(s.concordance_click)}
                  </p>
                  <p className="text-[10px] text-ink-muted">클릭 의향률(예측) ↔ CTR(실측)</p>
                </div>
                <div>
                  <p className="text-[11px] text-ink-tertiary">구매 예측 적중률</p>
                  <p
                    className={`text-2xl font-extrabold tabular-nums ${concordanceCls(s.concordance_purchase)}`}
                  >
                    {pct(s.concordance_purchase)}
                  </p>
                  <p className="text-[10px] text-ink-muted">구매의도(예측) ↔ CVR(실측)</p>
                </div>
              </div>
              <div className="h-1.5 w-full rounded-full bg-surface-1 overflow-hidden">
                <div
                  className={`h-full ${s.unlocked ? 'bg-green-500' : 'bg-primary'}`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              {!s.unlocked && (
                <p className="mt-2 text-[10px] text-ink-muted">
                  아직 데이터가 적어({s.n}/{s.unlock_threshold}건) 참고용이에요.{' '}
                  {s.unlock_threshold}건이 모이면 정밀 검증이 시작돼요.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function Page() {
  const router = useRouter();
  const [items, setItems] = useState<BeforeAfterItem[] | null>(null);
  const [calib, setCalib] = useState<CalibrationResponse | null>(null);
  const [rateLimited, setRateLimited] = useState<string | null>(null);
  const [simLoading, setSimLoading] = useState<string | null>(null); // 로딩 중인 campaign_id
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<'all' | BeforeAfterItem['verdict']>('all');

  const handleRunSim = useCallback(async (campaignId: string) => {
    setSimLoading(campaignId);
    try {
      const t = await api.management.campaignTargeting(campaignId);
      const params = new URLSearchParams({ from_campaign: campaignId });
      if (t.campaign_name) params.set('from_name', t.campaign_name);
      if (t.objective) params.set('objective', goalFromObjective(t.objective) ?? '');
      if (t.age_min != null) params.set('age_min', String(t.age_min));
      if (t.age_max != null) params.set('age_max', String(t.age_max));
      if (t.gender) params.set('gender', t.gender);
      if (t.ad_headline) params.set('ad_title', t.ad_headline);
      if (t.ad_body) params.set('ad_content', t.ad_body);
      if (t.category_id) params.set('category_id', String(t.category_id));
      if (t.service_class) params.set('service_class', String(t.service_class));
      if (t.suggested_persona_count) params.set('persona_count', String(t.suggested_persona_count));
      // fbcdn CORS는 브라우저 제한 — 시뮬 백엔드는 서버끼리 직접 접근 가능.
      // 실제 Meta CDN URL을 그대로 전달해 백엔드가 서버사이드로 이미지 가져오게 함.
      if (t.ad_image_url) params.set('ad_image_url', t.ad_image_url);
      router.push(`/simulation?${params.toString()}`);
    } catch {
      alert('타겟팅 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      setSimLoading(null);
    }
  }, [router]);

  const fetchData = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api.management.beforeAfter();
      setItems(r.items);
      setRateLimited(r.rate_limited ?? null);
      setFetchedAt(new Date());
    } catch {
      setItems([]);
    } finally {
      setRefreshing(false);
    }
    api.management
      .calibrationAnchors()
      .then(r => setCalib(r))
      .catch(() => {});
  }, []);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const counts: Record<BeforeAfterItem['verdict'], number> = {
    overperformed: 0,
    underperformed: 0,
    aligned: 0,
    unknown: 0,
  };
  for (const it of items ?? []) counts[it.verdict] += 1;
  const visible = (items ?? []).filter(it => filter === 'all' || it.verdict === filter);

  return (
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-ink">성과 비교</h1>
            <p className="text-sm text-ink-tertiary mt-1">
              시뮬 예측(집행 전)과 실제 성과(집행 후)를 나란히 봅니다 · 단위가 달라 방향만 비교해요
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 text-xs text-ink-tertiary">
            {fetchedAt && (
              <span>
                갱신{' '}
                {fetchedAt.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
            <button
              onClick={() => void fetchData()}
              disabled={refreshing}
              className="px-2.5 py-1.5 rounded-lg border border-line hover:border-primary hover:text-primary disabled:opacity-50 transition-colors"
            >
              {refreshing ? '불러오는 중…' : '↻ 새로고침'}
            </button>
          </div>
        </div>

        {/* 요약 + 필터 칩 — 판정별 개수가 곧 필터 */}
        {items !== null && items.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-1.5">
            <button
              onClick={() => setFilter('all')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-colors ${
                filter === 'all'
                  ? 'border-primary bg-primary-subtle text-primary'
                  : 'border-line text-ink-tertiary hover:border-primary'
              }`}
            >
              전체 {items.length}
            </button>
            {VERDICT_ORDER.filter(k => counts[k] > 0).map(k => (
              <button
                key={k}
                onClick={() => setFilter(f => (f === k ? 'all' : k))}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-colors ${
                  filter === k
                    ? 'border-primary bg-primary-subtle text-primary'
                    : 'border-line text-ink-tertiary hover:border-primary'
                }`}
              >
                {VERDICT[k].label} {counts[k]}
              </button>
            ))}
          </div>
        )}

        {/* 전/후 비교 — 주 화면 */}
        {items === null && <p className="text-sm text-ink-tertiary py-10 text-center">불러오는 중…</p>}
        {items !== null && visible.length > 0 && (
          <div className="space-y-3">
            {visible.map((it) => (
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
          <div className="rounded-2xl border border-line p-8 text-center">
            {rateLimited ? (
              <>
                <p className="text-sm text-amber-700 dark:text-amber-300">{rateLimited}</p>
                <p className="text-xs text-ink-muted mt-1">
                  Meta 요청 한도에 일시적으로 걸렸어요. 잠시 후 새로고침하면 실측이 표시돼요.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm text-ink-secondary">
                  아직 비교할 캠페인이 없어요.
                </p>
                <p className="text-xs text-ink-muted mt-1">
                  캠페인을 게재하면 집행 후(실측)가 채워지고, 그 광고로 시뮬을 돌리면 집행
                  전(예측)이 나란히 표시돼요.
                </p>
              </>
            )}
          </div>
        )}

        {/* 예측 정확도 검증 — 보조 정보라 목록 아래 접힌 상태로 */}
        <div className="mt-4">
          {calib && <CalibrationCard calib={calib} />}
        </div>

        <p className="mt-2 text-[11px] text-ink-muted">
          시뮬 예측(클릭 의향률·구매의도)과 실제 지표(CTR·CVR·ROAS)는 단위가 달라 서로 환산하지
          않고, 각자 기준선을 넘었는지로 방향만 비교해요 · CVR은 전환(구매·리드·가입 등)이 잡히면
          자동 계산 · ROAS는 구매 금액(전환가치)이 있을 때 표시돼요
        </p>
      </div>
  );
}
