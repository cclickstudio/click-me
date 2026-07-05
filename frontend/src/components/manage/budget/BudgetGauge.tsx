// 예산 게이지 — 한도 대비 소진 막대 + 90/95/100% 가드레일 '밴드' + 오늘 계획 페이스 마커.
import type { BudgetDecision } from './types';

const FILL: Record<BudgetDecision, string> = {
  allow: 'bg-[#3182F6]',
  warn: 'bg-amber-500',
  escalate: 'bg-red-500',
  block: 'bg-red-700',
};

export function BudgetGauge({
  spent,
  limit,
  ratio,
  decision,
  planPct,
}: {
  spent: number;
  limit: number;
  ratio: number;
  decision: BudgetDecision;
  planPct?: number | null; // 오늘까지의 계획 페이스(월 경과율 %) — 있으면 점선 마커 표시
}) {
  const pct = Math.min(ratio * 100, 100);
  const plan = planPct != null ? Math.min(Math.max(planPct, 0), 100) : null;
  return (
    <div>
      <div className="flex items-end justify-between mb-2">
        <span className="text-sm text-[#8B95A1]">
          소진 <b className="text-[#191F28] dark:text-[#F2F4F6]">₩{spent.toLocaleString()}</b> / 한도 ₩
          {limit.toLocaleString()}
        </span>
        <span className="text-2xl font-extrabold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">
          {(ratio * 100).toFixed(0)}%
        </span>
      </div>
      <div className="relative h-6 rounded-full bg-[#F2F4F6] dark:bg-[#2D3748] overflow-hidden">
        {/* 가드레일 밴드 — 90~95 경고(호박) · 95~100 차단(적색) 배경으로 위험 구간을 미리 보여줌 */}
        <div className="absolute inset-y-0 bg-amber-100 dark:bg-amber-900/30" style={{ left: '90%', width: '5%' }} />
        <div className="absolute inset-y-0 bg-red-100 dark:bg-red-900/30" style={{ left: '95%', width: '5%' }} />
        <div
          className={`relative h-full rounded-full ${FILL[decision]} transition-all`}
          style={{ width: `${pct}%` }}
        />
        {/* 90 / 95% 경계선 */}
        {[90, 95].map((m) => (
          <div
            key={m}
            className="absolute top-0 h-full border-l border-white/70 dark:border-black/40"
            style={{ left: `${m}%` }}
          />
        ))}
        {/* 오늘 계획 페이스 — 월 경과율 위치. 막대가 이 앞이면 여유, 넘었으면 과속. */}
        {plan != null && (
          <div
            className="absolute top-0 h-full border-l-2 border-dashed border-[#191F28]/60 dark:border-white/60"
            style={{ left: `${plan}%` }}
            title={`오늘까지 계획 페이스 ${Math.round(plan)}%`}
          />
        )}
      </div>
      <div className="relative h-4 mt-1 text-[10px] text-[#B0B8C1]">
        <span className="absolute left-0">0</span>
        {plan != null && plan > 8 && plan < 82 && (
          <span
            className="absolute -translate-x-1/2 text-[#4E5968] dark:text-[#9CA3AF]"
            style={{ left: `${plan}%` }}
          >
            오늘 계획 {Math.round(plan)}%
          </span>
        )}
        {/* 가드레일 라벨 — 90/95%가 좁은 타일에서 겹치지 않게 우측 끝 한 줄로 합친다.
            (막대의 호박·적색 밴드가 위치를 이미 보여줘 눈금 '100'은 생략) */}
        <span className="absolute right-0">경고 90% · 차단 95%</span>
      </div>
    </div>
  );
}
