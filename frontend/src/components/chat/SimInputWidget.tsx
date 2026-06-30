'use client';

// 채팅 안 시뮬레이션 입력 요약 위젯 — 실제로 돌린 입력값을 보여준다(입력 폼은 결과가 나오면 숨겨짐).
// 값은 위젯 data에 직접 담겨 영속화되므로 별도 조회 없이 새로고침에도 그대로 복원된다.
const cardCls =
  'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#1C2333] p-4';

const rowLabel = 'text-[11px] font-semibold text-[#8B95A1] dark:text-[#6B7280] shrink-0 w-16';
const rowValue = 'text-[12px] text-[#191F28] dark:text-[#F2F4F6] min-w-0';

export default function SimInputWidget({
  data,
}: {
  data?: {
    ad_title?: string;
    ad_content?: string;
    product_category?: string;
    ad_objective?: string;
    sample_size?: number;
  };
}) {
  const rows: { label: string; value: string }[] = [];
  if (data?.ad_title) rows.push({ label: '제품명', value: data.ad_title });
  if (data?.ad_content) rows.push({ label: '광고 설명', value: data.ad_content });
  if (data?.product_category) rows.push({ label: '카테고리', value: data.product_category });
  if (data?.ad_objective) rows.push({ label: '광고 목표', value: data.ad_objective });
  if (typeof data?.sample_size === 'number')
    rows.push({ label: '가상 소비자', value: `${data.sample_size}명` });

  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">🧪 시뮬레이션 입력</p>
      <div className="space-y-1.5">
        {rows.map((r) => (
          <div key={r.label} className="flex gap-2">
            <span className={rowLabel}>{r.label}</span>
            <span className={rowValue}>{r.value}</span>
          </div>
        ))}
        {rows.length === 0 && (
          <p className="text-[12px] text-[#B0B8C1]">입력 정보가 없어요.</p>
        )}
      </div>
    </div>
  );
}
