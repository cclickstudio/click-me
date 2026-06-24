// 생성/개선 모드 배지 — 제너레이터 목록·상세에서 공용 사용
export default function ModeBadge({ mode }: { mode?: string }) {
  const improve = mode === 'improve';
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-medium ${
        improve
          ? 'bg-[#FFF3E0] dark:bg-[#3A2A14] text-[#E8821A]'
          : 'bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]'
      }`}
    >
      {improve ? '개선' : '생성'}
    </span>
  );
}
