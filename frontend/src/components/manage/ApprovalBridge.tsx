// 🤝 승인(HITL) — Tier 판정·재라벨=A 설계 / 무승인 차단=B 강제. 공동 클라이맥스.
import type { RunResult, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

export function ApprovalBridge({
  run,
  decided,
  onApprove,
  onReject,
  mode,
}: {
  run: RunResult | null;
  decided: "approved" | "rejected" | null;
  onApprove: () => void;
  onReject: () => void;
  mode: ViewMode;
}) {
  return (
    <div className="my-6 rounded-2xl border-2 border-primary p-4 text-center bg-gradient-to-r from-[#2563EB]/[0.05] to-[#0F9D58]/[0.05]">
      <p className="text-sm font-bold text-ink mb-1">
        🤝 승인 (HITL) <RoleTag mode={mode} role="AB" contract="ApprovedAction ▶" />
      </p>
      {run?.relabeled && <p className="text-xs text-[#E5840F] mb-2">⚠ Tier 1▶3 재라벨됨 — 사용자 승인 필요</p>}
      {decided === null ? (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={onApprove}
            disabled={!run?.proposal}
            className="px-5 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-40"
          >
            적용 승인
          </button>
          <button
            onClick={onReject}
            disabled={!run?.proposal}
            className="px-5 py-2 border border-line text-sm rounded-lg disabled:opacity-40"
          >
            거절
          </button>
        </div>
      ) : (
        <p className="text-sm font-medium text-ink-tertiary">
          {decided === "approved"
            ? "✅ 승인됨"
            : "🚫 거절됨 — 무승인 액션은 어떤 경로로도 적용되지 않습니다"}
        </p>
      )}
    </div>
  );
}
