// 🅰 측정·진단 존 — 기대 vs 실측 노출 곡선(이상구간) + 진단 카드
'use client';

import dynamic from 'next/dynamic';
import type { RunResult, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

const MonitoringChart = dynamic(() => import('./MonitoringChart'), {
  ssr: false,
  loading: () => (
    <div className="h-[150px] animate-pulse rounded-xl bg-[#F2F4F6] dark:bg-[#2D3748]" />
  ),
});

export function AZone({ run, mode }: { run: RunResult; mode: ViewMode }) {
  const dx = run.diagnosis;
  return (
    <section className="flex-1 border rounded-2xl p-5 border-[#3182F6]/40 bg-[#3182F6]/[0.03]">
      <h2 className="text-sm font-bold text-[#3182F6] mb-3 flex items-center gap-2">
        📊 측정 · 진단 <RoleTag mode={mode} role="A" />
      </h2>
      <p className="text-xs text-[#8B95A1] mb-1">노출 추이 · 기대모델 vs 실측</p>
      <MonitoringChart run={run} />
      {dx && (
        <div className="mt-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
              🔍 {dx.hypothesis || dx.anomaly_type}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1]">
              {dx.source}
            </span>
          </div>
          <p className="text-xs text-[#8B95A1] mt-1">확신도 {Math.round(dx.confidence * 100)}%</p>
          <RoleTag mode={mode} role="A" contract="DiagnosisResult ▶" />
        </div>
      )}
    </section>
  );
}
