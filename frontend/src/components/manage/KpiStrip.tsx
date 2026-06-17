// 상단 KPI 4종 — 활성 캠페인·오늘 노출·오늘 지출·이상 감지
import type { RunResult } from "./types";

export function KpiStrip({ run }: { run: RunResult | null }) {
  const impressions = run?.snapshots.reduce((a, s) => a + s.impressions, 0) ?? 0;
  const spend = run?.snapshots.reduce((a, s) => a + s.spend_krw, 0) ?? 0;
  const anomalies = run?.anomaly_hours.length ? 1 : 0;
  const cards = [
    { label: "활성 캠페인", value: "1", alert: false },
    { label: "오늘 노출", value: impressions.toLocaleString(), alert: false },
    { label: "오늘 지출", value: `₩${spend.toLocaleString()}`, alert: false },
    { label: "이상 감지", value: String(anomalies), alert: anomalies > 0 },
  ];
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      {cards.map((c) => (
        <div
          key={c.label}
          className={`bg-white dark:bg-[#1C2333] border rounded-2xl p-5 ${
            c.alert ? "border-[#E5484D]" : "border-[#E5E8EB] dark:border-[#2D3748]"
          }`}
        >
          <p className="text-xs text-[#8B95A1] mb-1">{c.label}</p>
          <p className={`text-2xl font-bold ${c.alert ? "text-[#E5484D]" : "text-[#191F28] dark:text-[#F2F4F6]"}`}>
            {c.value}
          </p>
        </div>
      ))}
    </div>
  );
}
