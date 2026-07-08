// 생성/카드/개선 모드 배지 — 제너레이터 목록·상세에서 공용 사용
// improve=개선(주황) / create+carousel=카드(보라) / create+single=생성(파랑)
export default function ModeBadge({ mode, format }: { mode?: string; format?: string }) {
  const improve = mode === 'improve';
  const carousel = !improve && format === 'carousel';
  const label = improve ? '개선' : carousel ? '카드' : '생성';
  const cls = improve
    ? 'bg-[#FFF3E0] dark:bg-[#3A2A14] text-[#E8821A]'
    : carousel
      ? 'bg-[#F3EBFF] dark:bg-[#2A1E3F] text-[#6366F1]'
      : 'bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#2563EB]';
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${cls}`}>
      {label}
    </span>
  );
}
