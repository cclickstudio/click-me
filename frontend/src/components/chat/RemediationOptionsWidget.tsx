// 이상 조치 옵션 버튼 위젯 — consult meta의 옵션을 동적 렌더 + [기타] (이상 감지 C안)
'use client';

import { useState } from 'react';

const CIRCLED = ['①', '②', '③', '④', '⑤'];

export type RemediationOption = {
  index: number;
  action: string;
  tool_hint: string | null;
  label: string;
};

export type OptionSelectMeta = {
  kind: 'remediation_option_select';
  option_index: number;
  action: string;
  tool_hint: string | null;
  campaign_id: string;
  label: string;
};

export default function RemediationOptionsWidget({
  options,
  campaignId,
  onSelect,
  onEtc,
}: {
  options: RemediationOption[];
  campaignId: string;
  onSelect: (text: string, meta: OptionSelectMeta) => void;
  onEtc: () => void;
}) {
  // 선택은 1회 — 고르면 나머지 옵션 비활성(중복 전송·혼란 방지, 사용자 피드백 2026-07-04).
  // 로컬 상태라 세션 재로드 시 리셋되는 건 1차 범위 수용(스펙 §4). 후속 질문은 [기타]로.
  const [selected, setSelected] = useState<number | null>(null);

  const click = (o: RemediationOption) => {
    if (selected !== null) return; // 이미 선택함 — 재전송 방지
    setSelected(o.index);
    onSelect(`${o.index}번(${o.label}) 진행해줘`, {
      kind: 'remediation_option_select',
      option_index: o.index,
      action: o.action,
      tool_hint: o.tool_hint,
      campaign_id: campaignId,
      label: o.label,
    });
  };

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {options.map(o => (
        <button
          key={o.index}
          type="button"
          disabled={selected !== null}
          onClick={() => click(o)}
          className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
            selected === o.index
              ? 'border-[#3182F6] bg-[#3182F6]/10 text-[#3182F6]'
              : selected !== null
                ? 'border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] opacity-40'
                : 'border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] hover:border-[#3182F6]'
          }`}
        >
          {selected === o.index && '✓ '}
          {CIRCLED[o.index - 1] ?? o.index} {o.label}
        </button>
      ))}
      <button
        type="button"
        onClick={onEtc}
        className="rounded-lg border border-dashed border-[#E5E8EB] dark:border-[#2D3748] px-2.5 py-1.5 text-xs text-[#8B95A1]"
      >
        기타…
      </button>
    </div>
  );
}
