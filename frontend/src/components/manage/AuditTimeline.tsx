// 🤝 감사 로그 — append-only 이벤트 타임라인
import type { AuditEvent, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

export function AuditTimeline({ events, mode }: { events: AuditEvent[]; mode: ViewMode }) {
  if (events.length === 0) return null;
  return (
    <div className="mt-6 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4">
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">
        🧾 감사 로그 <RoleTag mode={mode} role="AB" />
      </p>
      <ul className="space-y-1">
        {events.map((e) => (
          <li key={e.event_id} className="text-xs text-[#8B95A1] flex gap-2">
            <span className="text-[#B0B8C1]">{new Date(e.occurred_at).toLocaleTimeString("ko-KR")}</span>
            <span className="font-mono">{e.category}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
