// 범용 카드 렌더러 — 레지스트리로 섹션 위임. 미등록 kind는 스킵(전방호환) + dev 로그.
import type { ReactNode } from 'react';
import type { CardSection, ChatCard, Tone } from '@/lib/chatCard';
import { SECTION_RENDERERS } from './sections';

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-[#F2F4F6] text-[#4E5968] dark:bg-[#2D3748] dark:text-[#9CA3AF]',
  muted: 'bg-[#F9FAFB] text-[#8B95A1] dark:bg-[#1C2333] dark:text-[#6B7280]',
  success: 'bg-[#E7F4EC] text-[#15803D] dark:bg-[#14321F] dark:text-[#86EFAC]',
  warning: 'bg-[#FEF3C7] text-[#B45309] dark:bg-[#3B2F0B] dark:text-[#FCD34D]',
  critical: 'bg-[#FEE2E2] text-[#B91C1C] dark:bg-[#3B1212] dark:text-[#FCA5A5]',
};

function renderSection(section: CardSection): ReactNode {
  const renderer = SECTION_RENDERERS[section.kind] as ((s: CardSection) => ReactNode) | undefined;
  if (!renderer) {
    // 미등록 섹션 kind — 렌더 스킵(전방호환). dev에서만 로깅.
    if (process.env.NODE_ENV !== 'production') {
      console.debug('[chat] unknown card section kind:', section.kind);
    }
    return null;
  }
  return renderer(section);
}

export default function ChatCardView({ card }: { card: ChatCard }) {
  const hasHeader = Boolean(card.title) || (card.badges?.length ?? 0) > 0;
  return (
    <div className="flex flex-col gap-3 px-4 py-3 rounded-xl bg-[#F2F4F6] dark:bg-[#252D3D] max-w-sm">
      {hasHeader && (
        <div className="flex flex-wrap items-center gap-1.5">
          {card.title && <span className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">{card.title}</span>}
          {card.badges?.map((b, i) => (
            <span key={i} className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${TONE_CLASS[b.tone]}`}>
              {b.label}
            </span>
          ))}
        </div>
      )}
      {card.sections.map((s, i) => (
        <div key={i}>{renderSection(s)}</div>
      ))}
    </div>
  );
}
