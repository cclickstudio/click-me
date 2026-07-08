// 🤝 감사 로그 — append-only 이벤트 타임라인
import type { AuditEvent, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";
import { formatKST } from "@/lib/datetime";

export function AuditTimeline({ events, mode }: { events: AuditEvent[]; mode: ViewMode }) {
  if (events.length === 0) return null;
  return (
    <div className="mt-6 rounded-2xl border border-line p-4">
      <p className="text-sm font-semibold text-ink mb-2">
        🧾 감사 로그 <RoleTag mode={mode} role="AB" />
      </p>
      <ul className="space-y-1">
        {events.map((e) => (
          <li key={e.event_id} className="text-xs text-ink-tertiary flex gap-2">
            <span className="text-ink-muted">{formatKST(e.occurred_at)}</span>
            <span className="font-mono">{e.category}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
