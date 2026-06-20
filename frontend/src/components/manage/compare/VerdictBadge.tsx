// 리프트 판정 배지 — 통과/주의/미달 공용 (A·B 뷰 재사용)
import type { LiftVerdict } from './types';

const STYLE: Record<LiftVerdict, { label: string; cls: string }> = {
  pass: { label: '통과', cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' },
  caution: { label: '주의', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' },
  fail: { label: '미달', cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' },
};

export function VerdictBadge({ verdict }: { verdict: LiftVerdict }) {
  const s = STYLE[verdict];
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold ${s.cls}`}>
      {s.label}
    </span>
  );
}
