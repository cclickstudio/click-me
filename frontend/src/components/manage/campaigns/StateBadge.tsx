// 캠페인 상태 배지 — active/under_review/paused/ended 등 공용
import type { CampaignState } from './types';

const STYLE: Record<CampaignState, { label: string; cls: string; dot: string }> = {
  active: { label: '진행중', cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300', dot: 'bg-green-500' },
  active_pending_review: { label: '게재중·심사', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300', dot: 'bg-amber-500' },
  under_review: { label: '심사중', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300', dot: 'bg-amber-500' },
  paused: { label: '일시정지', cls: 'bg-[#F2F4F6] text-ink-secondary dark:bg-[#2D3748]', dot: 'bg-[#8B95A1]' },
  draft: { label: '초안', cls: 'bg-[#F2F4F6] text-ink-secondary dark:bg-[#2D3748]', dot: 'bg-[#8B95A1]' },
  ended: { label: '종료', cls: 'bg-[#F2F4F6] text-ink-tertiary dark:bg-[#2D3748]', dot: 'bg-[#B0B8C1]' },
  archived: { label: '삭제됨', cls: 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400', dot: 'bg-red-400' },
};

export function StateBadge({ state }: { state: CampaignState }) {
  const s = STYLE[state];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}
