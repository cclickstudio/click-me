"use client";

const LIKERT_LABELS = ["전혀 없음", "낮음", "보통", "높음", "매우 높음"];

const SIGNAL_LABELS: Record<string, string> = {
  attention:         "주목도",
  sentiment:         "호감도",
  click_intent:      "클릭 의향",
  comprehension:     "이해도",
  recall:            "기억도",
  conversion_intent: "구매 의향",
};

interface DistributionChartProps {
  distribution: number[];
  title?: string;
  exploratory?: boolean;
  kobacoBadge?: boolean;
  className?: string;
}

export function DistributionChart({
  distribution,
  title,
  exploratory = false,
  kobacoBadge = false,
  className = "",
}: DistributionChartProps) {
  const mean = distribution.reduce((acc, p, i) => acc + p * (i / (distribution.length - 1)), 0);

  return (
    <div className={`space-y-2 ${className}`}>
      {(title || exploratory || kobacoBadge) && (
        <div className="flex items-center gap-2 flex-wrap">
          {title && <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{SIGNAL_LABELS[title] ?? title}</p>}
          {exploratory && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-[#FFF8E6] dark:bg-[#2D2000] text-[#F4A100] font-medium">
              탐색적
            </span>
          )}
          {kobacoBadge && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-[#E8F9F0] dark:bg-[#002D1A] text-[#00C471] font-medium">
              KOBACO 검증
            </span>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        {distribution.map((prob, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="w-14 text-right text-[#8B95A1] dark:text-[#6B7280] shrink-0">
              {LIKERT_LABELS[i] ?? `Level ${i + 1}`}
            </span>
            <div className="flex-1 bg-[#F2F4F6] dark:bg-[#252D3D] rounded-full h-4 overflow-hidden">
              <div
                className="h-full bg-[#3182F6] rounded-full transition-all duration-500"
                style={{ width: `${(prob * 100).toFixed(1)}%` }}
              />
            </div>
            <span className="w-10 text-[#4E5968] dark:text-[#9CA3AF] shrink-0">
              {(prob * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>

      <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">
        평균: {(mean * 5).toFixed(2)} / 5.0
      </p>
    </div>
  );
}
