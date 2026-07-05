// 🅱 개선·실행 존 — 재생성 후보 + 제안 카드 + 실행 결과
import { memo } from "react";
import type { ActionResult, Proposal, ViewMode } from "./types";
import { actionLabel } from "./types";
import { RoleTag } from "./RoleTag";

// memo — proposal·result·mode가 그대로면 무관한 부모 리렌더(스캔·busy)에서 스킵.
export const BZone = memo(function BZone({
  proposal,
  result,
  mode,
}: {
  proposal: Proposal | null;
  result: ActionResult | null;
  mode: ViewMode;
}) {
  const candidates = proposal?.evidence_metrics.candidates ?? [];
  const selected = proposal?.evidence_metrics.selected_candidate_id;
  return (
    <section className="flex-1 border rounded-2xl p-5 border-[#0F9D58]/40 bg-[#0F9D58]/[0.03]">
      <h2 className="text-sm font-bold text-[#0F9D58] mb-3 flex items-center gap-2">
        ✨ 개선 · 실행 <RoleTag mode={mode} role="B" />
      </h2>

      {candidates.length > 0 && (
        <>
      <p className="text-xs text-[#8B95A1] mb-2">🎨 재생성 후보 (시뮬 점수는 실성과 상관 미검증·참고용)</p>
      <div className="grid grid-cols-3 gap-2 mb-3">
        {candidates.map((c) => (
          <div
            key={c.candidate_id}
            className={`rounded-lg border p-2 text-center ${
              c.candidate_id === selected
                ? "border-[#0F9D58] bg-[#0F9D58]/10"
                : "border-[#E5E8EB] dark:border-[#2D3748]"
            }`}
          >
            <p className="text-[10px] text-[#8B95A1] truncate">{c.candidate_id.slice(0, 6)}</p>
            <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">{c.sim_score?.toFixed(2) ?? "-"}</p>
            {c.candidate_id === selected && <p className="text-[10px] text-[#0F9D58]">✓ 선택</p>}
          </div>
        ))}
      </div>
        </>
      )}

      {proposal && (
        <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-3 mb-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">📋 {actionLabel(proposal.action_type)}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FFF3E0] text-[#E5840F]">
              Tier {proposal.action_tier}
            </span>
          </div>
          {/* 예산 액션(증·감액)만 예산 변화를 보인다 — 소재·입찰·타겟은 예산 그대로라 줄을 숨김 */}
          {proposal.budget_after_krw !== proposal.budget_before_krw && (
            <p className="text-xs text-[#8B95A1] mt-1">
              예산 ₩{proposal.budget_before_krw.toLocaleString()} ▶ ₩{proposal.budget_after_krw.toLocaleString()}
            </p>
          )}
          <RoleTag mode={mode} role="B" contract="◀ ActionProposal" />
        </div>
      )}

      {result && (
        <div
          className={`rounded-xl border p-3 ${
            result.status === "failed" || result.status === "rejected" ? "border-[#E5484D]" : "border-[#0F9D58]"
          }`}
        >
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
            ⚙ 실행 결과: {result.status}
            {result.failure_reason ? ` (${result.failure_reason})` : ""}
          </p>
          <RoleTag mode={mode} role="B" contract="ActionResult ▶" />
        </div>
      )}
    </section>
  );
});
