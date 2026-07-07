// 아키텍처 보기 전용 소유자(🅰/🅱/🤝)·계약 라벨 — 사용자 보기에선 렌더 안 함
import type { ViewMode } from "./types";

const COLORS: Record<string, string> = { A: "#3182F6", B: "#0F9D58", AB: "#8B95A1" };

export function RoleTag({ mode, role, contract }: { mode: ViewMode; role: "A" | "B" | "AB"; contract?: string }) {
  if (mode !== "arch") return null;
  const label = role === "A" ? "🅰" : role === "B" ? "🅱" : "🤝";
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold" style={{ color: COLORS[role] }}>
      {label}
      {contract ? <span className="text-ink-tertiary">· {contract}</span> : null}
    </span>
  );
}
