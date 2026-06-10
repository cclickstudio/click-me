"use client";

const STAGES = [
  { key: "ad_analysis", label: "광고 분석" },
  { key: "persona_factory", label: "페르소나 생성" },
  { key: "exposure", label: "반응 시뮬레이션" },
  { key: "scoring", label: "SSR 채점" },
  { key: "aggregation", label: "집계" },
];

interface SimulatorProgressProps {
  currentStage: string;
  pct: number;
  message?: string;
}

export function SimulatorProgress({ currentStage, pct, message }: SimulatorProgressProps) {
  const currentIdx = STAGES.findIndex((s) => s.key === currentStage);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-[#8B95A1] dark:text-[#6B7280]">{message ?? "시뮬레이션 진행 중..."}</span>
          <span className="font-medium text-[#191F28] dark:text-[#F2F4F6]">{pct}%</span>
        </div>
        <div className="w-full bg-[#F2F4F6] dark:bg-[#252D3D] rounded-full h-3 overflow-hidden">
          <div
            className="h-full bg-[#3182F6] rounded-full transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <div className="space-y-2">
        {STAGES.map((stage, i) => {
          const done = i < currentIdx;
          const active = i === currentIdx;

          const circleClass = done
            ? "bg-[#00C471] text-white"
            : active
            ? "bg-[#3182F6] text-white"
            : "bg-[#E5E8EB] dark:bg-[#2D3748] text-[#B0B8C1] dark:text-[#4B5563]";

          const labelClass = done
            ? "text-[#00C471]"
            : active
            ? "text-[#3182F6] font-medium"
            : "text-[#B0B8C1] dark:text-[#4B5563]";

          return (
            <div key={stage.key} className="flex items-center gap-2 text-sm">
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${circleClass}`}
              >
                {done ? "✓" : i + 1}
              </span>
              <span className={labelClass}>{stage.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
