// 표 셀 인라인 KPI 입력 — '미설정'(전환 데이터 없음)일 때만 쓰는 수동 추정 입력
'use client';

import { useEffect, useState } from 'react';

export function KpiInput({
  manual,
  unit,
  onCommit,
}: {
  manual?: number; // 저장된 수동 추정값
  unit: '%' | 'x';
  onCommit: (raw: string) => void;
}) {
  const [text, setText] = useState(manual != null ? String(manual) : '');
  // 외부(서버 로드 등) 값 변경 시 동기화
  useEffect(() => {
    setText(manual != null ? String(manual) : '');
  }, [manual]);

  const isSet = manual != null;
  return (
    <span className="inline-flex items-center justify-end gap-0.5">
      <input
        type="number"
        inputMode="decimal"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => onCommit(text)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        }}
        placeholder="입력"
        title="전환 추적 전 — 직접 추정값 입력"
        className={`w-12 rounded border border-dashed bg-transparent px-1 py-0.5 text-right text-sm tabular-nums focus:border-solid focus:border-[#3182F6] ${
          isSet
            ? 'border-amber-300 text-amber-700 dark:border-amber-700/60 dark:text-amber-400'
            : 'border-[#C9CED6] text-[#191F28] dark:border-[#3A4452] dark:text-[#F2F4F6]'
        }`}
      />
      <span className="text-[#8B95A1]">{unit}</span>
      {isSet && <span className="text-[10px] font-medium text-amber-600">추정</span>}
    </span>
  );
}
