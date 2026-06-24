// 예산 게이지 — 한도 대비 소진 막대 + 90/95/100% 눈금 + decision별 색
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
}: {
  spent: number;
  limit: number;
  ratio: number;
  decision: BudgetDecision;
}) {
  const pct = Math.min(ratio * 100, 100);
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
        <div className={`h-full ${FILL[decision]} transition-all`} style={{ width: `${pct}%` }} />
        {/* 90 / 95% 눈금 */}
        {[90, 95].map((m) => (
          <div
            key={m}
            className="absolute top-0 h-full border-l border-white/70 dark:border-black/40"
            style={{ left: `${m}%` }}
          />
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-[#B0B8C1] mt-1">
        <span>0</span>
        <span style={{ marginRight: '8%' }}>90% 경고</span>
        <span>95% 차단 · 100%</span>
      </div>
    </div>
  );
}
