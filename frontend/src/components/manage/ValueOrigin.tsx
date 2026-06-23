// 값 출처 구분 — Meta 실측이 아닌 값(내 설정·계산)에 태그를 붙여 '사실'과 섞이지 않게 한다.
// 실측은 기본 표시(태그 없음), 내가 정한 값/계산값만 표식해 오해를 막는다.
type Origin = 'setting' | 'computed';

const ORIGIN: Record<Origin, { label: string; cls: string }> = {
  setting: {
    label: '내 설정',
    cls: 'bg-violet-50 text-violet-600 border-violet-200 dark:bg-violet-900/20 dark:text-violet-300 dark:border-violet-900/40',
  },
  computed: {
    label: '계산',
    cls: 'bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-900/40',
  },
};

export function OriginTag({ origin }: { origin: Origin }) {
  const o = ORIGIN[origin];
  return (
    <span
      className={`ml-1 inline-block align-middle rounded border px-1 text-[9px] font-medium leading-[1.5] ${o.cls}`}
    >
      {o.label}
    </span>
  );
}

// 출처 범례 — 화면 상단에 한 줄로 세 계층을 학습시킨다.
export function OriginLegend({ className = '' }: { className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#8B95A1] ${className}`}>
      <span className="inline-flex items-center gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-[#3182F6]" />
        Meta 실측
      </span>
      <span className="inline-flex items-center gap-1">
        <OriginTag origin="setting" />
        내가 정한 값
      </span>
      <span className="inline-flex items-center gap-1">
        <OriginTag origin="computed" />
        실측을 내 설정과 합쳐 계산(일부 추정)
      </span>
    </div>
  );
}
