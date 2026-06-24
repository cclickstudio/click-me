'use client';

// 채팅 /분석 — 프로젝트의 과거 시뮬·시안 활동을 집계해 한눈에 요약하는 위젯.
// projectId로 시뮬/생성 목록을 직접 조회(읽기 전용)해 건수·완료율·총 가상소비자·최근 활동을 보여준다.
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { formatKST } from '@/lib/datetime';

const cardCls =
  'mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#1C2333] p-4';

type Row = { id: string; title: string; status?: string; created_at?: string; sample_size?: number };

const fmtDate = formatKST;

const isDone = (s?: string) => (s ?? '').toLowerCase() === 'completed';
const isFailed = (s?: string) => (s ?? '').toLowerCase() === 'failed';

export default function AnalysisSummaryWidget({ projectId }: { projectId?: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [sims, setSims] = useState<Row[]>([]);
  const [gens, setGens] = useState<Row[]>([]);

  useEffect(() => {
    if (!projectId) {
      setErr('프로젝트를 먼저 선택하세요.');
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [s, g] = await Promise.all([
          api.projects.simulations(projectId, 100),
          api.projects.generations(projectId, 100),
        ]);
        if (cancelled) return;
        setSims(
          (s as Record<string, unknown>[]).map(r => ({
            id: String(r.id),
            title: (r.ad_title as string) || '(제목 없음)',
            status: r.status as string | undefined,
            created_at: r.created_at as string | undefined,
            sample_size: r.sample_size as number | undefined,
          })),
        );
        setGens(
          (g as Record<string, unknown>[]).map(r => ({
            id: String(r.id),
            title: (r.product_name as string) || '(제목 없음)',
            status: r.status as string | undefined,
            created_at: r.created_at as string | undefined,
          })),
        );
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : '분석 조회 실패');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (loading) {
    return (
      <div className={cardCls}>
        <div className="flex items-center gap-2 text-sm text-[#8B95A1]">
          <span className="w-4 h-4 border-2 border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] rounded-full animate-spin" />
          성과를 분석하고 있어요...
        </div>
      </div>
    );
  }
  if (err) {
    return (
      <div className={cardCls}>
        <p className="text-sm text-[#F04452]">분석 실패: {err}</p>
      </div>
    );
  }

  const simDone = sims.filter(s => isDone(s.status)).length;
  const personas = sims.reduce((a, s) => a + (s.sample_size ?? 0), 0);
  const genDone = gens.filter(g => isDone(g.status)).length;
  const genFailed = gens.filter(g => isFailed(g.status)).length;
  const recentSims = sims.slice(0, 3);
  const recentGens = gens.slice(0, 3);

  const statCls = 'rounded-lg bg-white dark:bg-[#252D3D] px-3 py-2.5';
  const numCls = 'text-lg font-bold text-[#191F28] dark:text-[#F2F4F6]';
  const capCls = 'text-[11px] text-[#8B95A1] dark:text-[#6B7280]';

  return (
    <div className={cardCls}>
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
        📊 활동 요약
      </p>
      {sims.length === 0 && gens.length === 0 ? (
        <p className="text-[12px] text-[#8B95A1]">아직 이 프로젝트의 시뮬레이션·생성 기록이 없어요.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div className={statCls}>
              <p className={numCls}>
                {sims.length}
                <span className="text-[11px] font-normal text-[#8B95A1]"> 건</span>
              </p>
              <p className={capCls}>시뮬레이션 (완료 {simDone})</p>
            </div>
            <div className={statCls}>
              <p className={numCls}>
                {gens.length}
                <span className="text-[11px] font-normal text-[#8B95A1]"> 건</span>
              </p>
              <p className={capCls}>광고 생성 (완료 {genDone}{genFailed ? ` · 실패 ${genFailed}` : ''})</p>
            </div>
            <div className={statCls}>
              <p className={numCls}>
                {personas.toLocaleString()}
                <span className="text-[11px] font-normal text-[#8B95A1]"> 명</span>
              </p>
              <p className={capCls}>누적 가상 소비자</p>
            </div>
            <div className={statCls}>
              <p className={numCls}>
                {sims.length + gens.length}
                <span className="text-[11px] font-normal text-[#8B95A1]"> 건</span>
              </p>
              <p className={capCls}>전체 실행</p>
            </div>
          </div>
          {recentSims.length > 0 && (
            <div className="mb-2">
              <p className="text-[11px] font-semibold text-[#8B95A1] mb-1">최근 시뮬레이션</p>
              <ul className="space-y-1">
                {recentSims.map(s => (
                  <li key={s.id}>
                    <button
                      onClick={() => router.push(`/simulation/${s.id}`)}
                      className="w-full flex items-center justify-between gap-2 text-[12px] text-left rounded-lg px-2 py-1.5 hover:bg-white dark:hover:bg-[#252D3D] transition-colors"
                    >
                      <span className="truncate text-[#191F28] dark:text-[#F2F4F6]">{s.title}</span>
                      <span className="shrink-0 text-[11px] text-[#8B95A1]">{fmtDate(s.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {recentGens.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-[#8B95A1] mb-1">최근 광고 생성</p>
              <ul className="space-y-1">
                {recentGens.map(g => (
                  <li key={g.id}>
                    <button
                      onClick={() => router.push(`/generations/${g.id}`)}
                      className="w-full flex items-center justify-between gap-2 text-[12px] text-left rounded-lg px-2 py-1.5 hover:bg-white dark:hover:bg-[#252D3D] transition-colors"
                    >
                      <span className="truncate text-[#191F28] dark:text-[#F2F4F6]">{g.title}</span>
                      <span className="shrink-0 text-[11px] text-[#8B95A1]">{fmtDate(g.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
