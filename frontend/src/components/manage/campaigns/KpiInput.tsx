// 표 셀 인라인 KPI 입력 — 전환 추적 전 CVR·ROAS를 수동(추정)으로 직접 입력
'use client';

import { useEffect, useState } from 'react';

export function KpiInput({
  manual,
  measured,
  unit,
  onCommit,
}: {
  manual?: number; // 수동 입력값(있으면 추정)
  measured: number | null; // 실측 숫자(null=전환 추적 전·미설정)
  unit: '%' | 'x';
  onCommit: (raw: string) => void;
}) {
  const display = manual ?? measured ?? null;
  const [text, setText] = useState(display != null ? String(display) : '');
  // 데이터 갱신·외부 변경 시 표시값 동기화
  useEffect(() => {
    setText(display != null ? String(display) : '');
  }, [display]);

  const isManual = manual != null;
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
        title={isManual ? '수동 입력(추정값)' : '클릭해 직접 입력 — 추정값'}
        className={`w-12 rounded border border-dashed bg-transparent px-1 py-0.5 text-right text-sm tabular-nums focus:border-solid focus:border-[#3182F6] ${
          isManual
            ? 'border-amber-300 text-amber-700 dark:border-amber-700/60 dark:text-amber-400'
            : 'border-[#C9CED6] text-[#191F28] dark:border-[#3A4452] dark:text-[#F2F4F6]'
        }`}
      />
      <span className="text-[#8B95A1]">{unit}</span>
      {isManual && <span className="text-[10px] font-medium text-amber-600">추정</span>}
    </span>
  );
}
