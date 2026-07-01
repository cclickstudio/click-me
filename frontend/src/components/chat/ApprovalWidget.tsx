'use client';

// 개선 루프 HITL 카드 — 시뮬 결과가 약할 때 수락/거절로 다음 단계(개선 시안·재시뮬)를 진행
import { useState } from 'react';

export type ApprovalSpec = {
  action: string; // run_generator | rerun_simulation
  label: string;
  reasons?: string[];
};

export default function ApprovalWidget({
  approval,
  onAccept,
  disabled,
}: {
  approval: ApprovalSpec;
  onAccept: (action: string) => void;
  disabled?: boolean;
}) {
  const [decided, setDecided] = useState<null | 'accepted' | 'declined'>(null);

  return (
    <div className="mt-1 w-full rounded-xl border border-[#3182F6]/30 bg-[#F5F9FF] dark:bg-[#16243C] px-4 py-3">
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-xs font-bold text-[#3182F6]">개선 제안</span>
      </div>
      {approval.reasons && approval.reasons.length > 0 && (
        <ul className="mb-3 space-y-0.5">
          {approval.reasons.map((r, i) => (
            <li key={i} className="text-xs text-[#4E5968] dark:text-[#9CA3AF]">
              · {r}
            </li>
          ))}
        </ul>
      )}
      {decided === null ? (
        <div className="flex gap-2">
          <button
            disabled={disabled}
            onClick={() => {
              setDecided('accepted');
              onAccept(approval.action);
            }}
            className="px-3 py-1.5 rounded-lg bg-[#3182F6] text-white text-xs font-semibold hover:bg-[#1B6EEB] disabled:opacity-40 transition-colors"
          >
            {approval.label} →
          </button>
          <button
            disabled={disabled}
            onClick={() => setDecided('declined')}
            className="px-3 py-1.5 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] text-xs font-semibold hover:bg-[#F2F4F6] dark:hover:bg-[#252D3D] disabled:opacity-40 transition-colors"
          >
            나중에
          </button>
        </div>
      ) : (
        <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">
          {decided === 'accepted' ? '진행할게요.' : '알겠어요. 필요할 때 다시 말씀해주세요.'}
        </p>
      )}
    </div>
  );
}
