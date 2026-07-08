// 🅰 측정·진단 존 — 기대 vs 실측 노출 곡선(이상구간) + 진단 카드
'use client';

import { memo } from 'react';
import dynamic from 'next/dynamic';
import type { RunResult, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

const MonitoringChart = dynamic(() => import('./MonitoringChart'), {
  ssr: false,
  loading: () => (
    <div className="h-[150px] animate-pulse rounded-xl bg-surface-1" />
  ),
});

// memo — 스캔·busy 등 무관한 부모 리렌더 때 run·mode가 그대로면 차트째 스킵.
export const AZone = memo(function AZone({ run, mode }: { run: RunResult; mode: ViewMode }) {
  const dx = run.diagnosis;
  return (
    <section className="flex-1 border rounded-2xl p-5 border-primary/40 bg-primary/[0.03]">
      <h2 className="text-sm font-bold text-primary mb-3 flex items-center gap-2">
        📊 측정 · 진단 <RoleTag mode={mode} role="A" />
      </h2>
      <p className="text-xs text-ink-tertiary mb-1">노출 추이 · 기대모델 vs 실측</p>
      <MonitoringChart run={run} />
      {dx && (
        <div className="mt-3 rounded-xl border border-line p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-ink">
              🔍 {dx.hypothesis || dx.anomaly_type}
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-surface-1 text-ink-tertiary">
              {dx.source}
            </span>
          </div>
          <p className="text-xs text-ink-tertiary mt-1">확신도 {Math.round(dx.confidence * 100)}%</p>
          <RoleTag mode={mode} role="A" contract="DiagnosisResult ▶" />
        </div>
      )}
    </section>
  );
});
