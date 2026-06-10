interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  trend?: "up" | "down" | "neutral";
  className?: string;
}

export function KpiCard({ label, value, sub, trend, className = "" }: KpiCardProps) {
  const subColor =
    trend === "up"
      ? "text-[#00C471]"
      : trend === "down"
      ? "text-[#F04452]"
      : "text-[#8B95A1] dark:text-[#6B7280]";

  return (
    <div className={`bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-5 flex flex-col gap-1 transition-colors ${className}`}>
      <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">{label}</p>
      <p className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">{value}</p>
      {sub && <p className={`text-xs ${subColor}`}>{sub}</p>}
    </div>
  );
}
