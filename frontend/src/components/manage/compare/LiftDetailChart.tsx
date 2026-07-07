// B 뷰 — 선택 게시물의 오가닉 vs 광고 비교 (Recharts 그룹 막대)
'use client';

import dynamic from 'next/dynamic';
import type { BoardRow } from './types';

// 차트는 펼칠 때만 로드(번들 분리, SSR 끄기 — Recharts는 DOM 측정형)
const LiftBarsChart = dynamic(() => import('./LiftBarsChart'), {
  ssr: false,
  loading: () => (
    <div className="h-[220px] animate-pulse rounded-xl bg-surface-1" />
  ),
});

export function LiftDetailChart({ row }: { row: BoardRow }) {
  return (
    <div className="rounded-2xl border border-line px-5 py-4">
      <p className="font-bold text-ink mb-3">
        선택: {row.title} — 도달·노출 비교
      </p>
      <LiftBarsChart row={row} />
    </div>
  );
}
