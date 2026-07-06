// 전환 퍼널 — 노출→클릭→전환 실측 단계를 좁아지는 막대로, 단계 사이엔 실측 전환율(CTR·CVR).
// 넓이는 sqrt 비율(자릿수 차이가 커도 형태 유지) + 최소 14%. 전환 미설정(null)은 회색 '미설정'.

function widthPct(value: number, max: number): number {
  if (max <= 0 || value <= 0) return 14;
  return Math.max(Math.sqrt(value / max) * 100, 14);
}

export function ConversionFunnel({
  impressions,
  clicks,
  conversions,
  ctr,
  cvr,
}: {
  impressions: number;
  clicks: number;
  conversions: number | null; // 전환 추적 미설정이면 null
  ctr: number; // 0~1 실측(전체 클릭 기준)
  cvr: number | null; // 0~1 실측(링크 클릭 기준 — 분모가 달라요)
}) {
  const stages = [
    { label: '노출', value: impressions, unit: '회', bar: 'bg-[#3182F6]' },
    { label: '클릭', value: clicks, unit: '회', bar: 'bg-[#5B9DF9]' },
    {
      label: '전환',
      value: conversions,
      unit: '건',
      bar: conversions == null ? 'bg-[#D1D6DB] dark:bg-[#4B5563]' : 'bg-[#22C55E]',
    },
  ] as const;
  const rates = [
    `CTR ${(ctr * 100).toFixed(1)}%`,
    conversions == null ? '전환 추적 미설정' : `CVR ${((cvr ?? 0) * 100).toFixed(1)}%`,
  ];

  return (
    <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-4">
      <p className="text-[12px] font-semibold text-[#4E5968] dark:text-[#9CA3AF]">전환 퍼널</p>
      <p className="text-[10px] text-[#8B95A1] mb-3">
        노출→클릭→전환 실측 · CVR은 링크 클릭 기준(CTR의 전체 클릭과 분모가 달라요)
      </p>
      <div className="space-y-0.5">
        {stages.map((s, i) => (
          <div key={s.label}>
            {i > 0 && (
              <p className="py-0.5 text-center text-[10px] text-[#8B95A1]">▼ {rates[i - 1]}</p>
            )}
            <div className="flex items-center gap-2">
              <span className="w-8 shrink-0 text-[11px] text-[#8B95A1]">{s.label}</span>
              <div className="relative h-8 flex-1">
                <div
                  className={`absolute left-1/2 top-0 h-full -translate-x-1/2 rounded-lg ${s.bar} flex items-center justify-center transition-all`}
                  style={{ width: `${widthPct(s.value ?? 0, impressions)}%` }}
                >
                  <span className="px-2 text-[11px] font-bold text-white whitespace-nowrap tabular-nums">
                    {s.value == null ? '미설정' : `${s.value.toLocaleString()}${s.unit}`}
                  </span>
                </div>
              </div>
              <span className="w-8 shrink-0" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
