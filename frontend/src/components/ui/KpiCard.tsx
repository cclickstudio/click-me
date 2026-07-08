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
      ? "text-success"
      : trend === "down"
      ? "text-danger"
      : "text-ink-tertiary";

  return (
    <div className={`bg-surface-2 border border-line rounded-2xl p-5 flex flex-col gap-1 transition-colors ${className}`}>
      <p className="text-xs text-ink-tertiary">{label}</p>
      <p className="text-2xl font-bold text-ink">{value}</p>
      {sub && <p className={`text-xs ${subColor}`}>{sub}</p>}
    </div>
  );
}
