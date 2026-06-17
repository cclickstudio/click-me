// 우측 끝 — 증분 리프트 검증 패널 (광고가 오가닉 대비 만든 추가 성과 + 판정)
import type { LiftResult } from './types';
import { rate } from './types';
import { VerdictBadge } from './VerdictBadge';

export function LiftPanel({ lift }: { lift: LiftResult }) {
  const organicEr = rate(lift.organic.engagement, lift.organic.impressions);
  const paidCtr = rate(lift.paid.clicks, lift.paid.impressions);
  return (
    <div className="w-full lg:w-[360px] rounded-2xl bg-[#0F172A] text-white p-5">
      <h3 className="font-bold">증분 리프트 검증</h3>
      <p className="text-xs text-[#94A3B8] mt-0.5">광고가 오가닉 대비 추가로 만든 성과</p>

      <div className="mt-5">
        <p className="text-xs text-[#94A3B8]">증분 도달 (Δ Reach)</p>
        <p className="text-3xl font-extrabold text-green-400 tabular-nums">
          +{lift.reach_lift_abs.toLocaleString()}
        </p>
        <p className="text-[11px] text-[#64748B]">
          ×{lift.reach_lift_ratio} (오가닉 {lift.organic.reach.toLocaleString()} → 광고{' '}
          {lift.paid.reach.toLocaleString()})
        </p>
      </div>

      <div className="mt-4 pt-4 border-t border-[#1E293B]">
        <p className="text-xs text-[#94A3B8]">증분 노출 (Δ Impr.)</p>
        <p className="text-2xl font-extrabold text-green-400 tabular-nums">
          +{lift.impressions_lift_abs.toLocaleString()}
        </p>
      </div>

      <div className="mt-4 pt-4 border-t border-[#1E293B]">
        <p className="text-xs text-[#94A3B8]">참여 효율 비교</p>
        <p className="text-base font-bold text-amber-400">
          오가닉 {organicEr.toFixed(1)}% vs 광고 CTR {paidCtr.toFixed(1)}%
        </p>
        <p className="text-[11px] text-[#64748B]">도달·효율은 지표 정의가 달라 직접 비교는 참고용</p>
      </div>

      <div className="mt-5 flex items-center gap-2">
        <VerdictBadge verdict={lift.verdict} />
        <span className="text-xs text-[#94A3B8]">증분 도달 ×3↑ 통과 · ×1.5~3 주의 · 그 미만 미달</span>
      </div>

      <p className="mt-4 text-[11px] text-[#64748B]">
        * 도달 중복 보정 전 단순 배수 · 증분은 추정(exploratory) · 신뢰구간(CI)은 후속
      </p>
    </div>
  );
}
