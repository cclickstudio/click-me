// Deep Agent 계획(Planning) 체크리스트 — plan→act→observe를 가시화하는 todo 리스트.
'use client';

export type PlanStep = {
  step: string;
  status: 'pending' | 'in_progress' | 'completed';
};

function StatusIcon({ status }: { status: PlanStep['status'] }) {
  if (status === 'completed') {
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="#15B66E"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 mt-0.5">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    );
  }
  if (status === 'in_progress') {
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        className="shrink-0 mt-0.5 animate-spin"
        style={{ animationDuration: '1.2s' }}
        fill="none"
        stroke="#2563EB"
        strokeWidth="2.5"
        strokeLinecap="round">
        <path d="M21 12a9 9 0 1 1-6.219-8.56" />
      </svg>
    );
  }
  return (
    <span className="shrink-0 mt-1 w-3 h-3 rounded-full border-2 border-[#D1D6DB] dark:border-[#4B5563]" />
  );
}

// 계획(todo) 리스트 — 빈 계획(단순 질문)이면 렌더하지 않는다.
export default function PlanChecklist({ plan }: { plan?: PlanStep[] }) {
  if (!plan || plan.length === 0) return null;
  const done = plan.filter(p => p.status === 'completed').length;
  return (
    <div className="mt-1 rounded-xl border border-line bg-surface-1 px-3 py-2.5">
      <div className="flex items-center gap-1.5 mb-1.5">
        <svg
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#8B95A1"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round">
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
        <span className="text-[11px] font-semibold text-ink-secondary">
          실행 계획 {done}/{plan.length}
        </span>
      </div>
      <ul className="space-y-1">
        {plan.map((p, i) => (
          <li key={i} className="flex items-start gap-2">
            <StatusIcon status={p.status} />
            <span
              className={`text-xs leading-snug ${
                p.status === 'completed'
                  ? 'text-ink-tertiary line-through'
                  : p.status === 'in_progress'
                    ? 'text-ink font-medium'
                    : 'text-ink-secondary'
              }`}>
              {p.step}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
