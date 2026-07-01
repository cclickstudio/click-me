'use client';
// 시뮬 결과 라우트 — 실행 직후(sessionStorage 전체 데이터) 또는 콜드/패널 진입(API db-result) 모두 처리.
// 삭제·복원은 결과 데이터엔 없는 메타(deleted_at·project_id)를 별도 조회해 액션 바로 제공한다.

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { SimulationResultView } from '@/components/simulator/SimulationResultView';
import { api } from '@/lib/api';
import { getToken } from '@/lib/authApi';
import { useProjects } from '@/components/ProjectContext';
import { loadSimResult } from '@/lib/simResultStore';
import type { ReportView, SimRunResult } from '@/lib/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// 삭제/복원에 필요한 메타 — 결과 데이터엔 없어 별도 조회(DB 미저장 시 없음 → 버튼 숨김)
type SimMeta = { project_id: string; deleted_at: string | null };

export default function SimulationResultPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { refreshDetails } = useProjects();
  const [result, setResult] = useState<SimRunResult | null>(null);
  const [adTitle, setAdTitle] = useState<string | undefined>();
  const [adDescription, setAdDescription] = useState<string | undefined>();
  // DB에 저장된 통합 리포트 — 토론을 다시 돌리지 않아도 최종 리포트 복원.
  const [savedReport, setSavedReport] = useState<ReportView | null>(null);
  const [meta, setMeta] = useState<SimMeta | null>(null);
  const [acting, setActing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    // 저장된 통합 리포트는 진입 경로와 무관하게 병렬로 복원 시도(없으면 null, 실패 무시).
    api.debate
      .savedReport(id)
      .then(rv => {
        if (alive) setSavedReport(rv);
      })
      .catch(() => {
        /* 리포트 복원 실패는 무시 — 결과 화면은 떠야 함. */
      });

    // 삭제/복원용 메타 — DB에 저장된 시뮬이면 deleted_at·project_id 확보(없으면 버튼 숨김).
    fetch(`${API_BASE}/api/projects/simulations/${id}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (alive && d) setMeta({ project_id: d.project_id, deleted_at: d.deleted_at });
      })
      .catch(() => {
        /* 메타 없으면 삭제/복원 버튼만 숨김 — 결과 표시엔 영향 없음. */
      });

    // 1) 방금 실행한 결과(전체 데이터)가 sessionStorage에 있으면 그대로 사용.
    //    단, 옛 코드 시절 캐시엔 presigned S3 URL이 박혀 있을 수 있으므로(자격증명 노출·만료),
    //    그런 캐시는 무시하고 db-result(프록시 URL)로 새로 받는다.
    const stored = loadSimResult(id);
    const cachedAsset = stored?.result?.ad_asset_url ?? '';
    const cachedIsPresigned =
      cachedAsset.includes('amazonaws.com') ||
      /[?&](X-Amz-|AWSAccessKeyId)/i.test(cachedAsset);
    if (stored && !cachedIsPresigned) {
      setResult(stored.result);
      setAdTitle(stored.adTitle);
      setAdDescription(stored.adDescription);
      setLoading(false);
      return;
    }

    // 2) 콜드·패널 진입 — DB에서 조회. 404면 결과 없음.
    api.simulation
      .dbResult(id)
      .then(r => {
        if (!alive) return;
        setResult(r);
      })
      .catch(e => {
        if (!alive) return;
        const msg = e instanceof Error ? e.message : '결과를 불러올 수 없습니다.';
        setError(msg.includes('404') ? '결과가 없습니다.' : msg);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [id]);

  const handleDelete = async () => {
    if (!meta) return;
    if (!confirm('이 시뮬레이션을 삭제할까요?\n결과·페르소나 반응·보고서가 함께 삭제됩니다.')) return;
    setActing(true);
    const res = await fetch(`${API_BASE}/api/projects/simulations/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!res.ok) {
      setActing(false);
      alert('삭제에 실패했습니다.');
      return;
    }
    await refreshDetails(meta.project_id); // 패널 카운트 실시간 반영
    router.push(`/projects/${meta.project_id}`);
  };

  const handleRestore = async () => {
    if (!meta) return;
    setActing(true);
    const res = await fetch(`${API_BASE}/api/projects/simulations/${id}/restore`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    setActing(false);
    if (!res.ok) {
      alert('복원에 실패했습니다.');
      return;
    }
    setMeta(m => (m ? { ...m, deleted_at: null } : m));
    await refreshDetails(meta.project_id); // 패널 카운트 실시간 반영
  };

  // 삭제/복원 액션 — 결과 헤더('시뮬레이터 결과') 우측에 한 row로 붙인다(DB 저장 시만).
  const headerAction = meta ? (
    <div className='flex items-center gap-2'>
      {meta.deleted_at && (
        <span className='px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 dark:bg-red-900/20 text-red-600'>
          삭제됨
        </span>
      )}
      {meta.deleted_at ? (
        <button
          onClick={handleRestore}
          disabled={acting}
          className='px-3 py-1.5 rounded-full text-sm font-medium text-[#3182F6] border border-[#3182F6]/30 hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors disabled:opacity-40'
        >
          {acting ? '복원 중...' : '복원'}
        </button>
      ) : (
        <button
          onClick={handleDelete}
          disabled={acting}
          className='flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-red-500 border border-red-200 dark:border-red-900/40 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40'
        >
          <svg width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'>
            <polyline points='3 6 5 6 21 6' />
            <path d='M19 6l-1 14H6L5 6' />
            <path d='M10 11v6' />
            <path d='M14 11v6' />
            <path d='M9 6V4h6v2' />
          </svg>
          {acting ? '삭제 중...' : '삭제'}
        </button>
      )}
    </div>
  ) : null;

  return (
    <>
      {loading && (
        <div className='px-8 py-16 max-w-5xl mx-auto text-center'>
          <div className='inline-block w-8 h-8 border-4 border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] dark:border-t-[#5B9DF9] rounded-full animate-spin' />
          <p className='mt-4 text-sm text-[#8B95A1] dark:text-[#6B7280]'>
            결과를 불러오는 중...
          </p>
        </div>
      )}

      {!loading && error && (
        <div className='px-8 py-16 max-w-5xl mx-auto text-center'>
          <p className='text-sm text-[#DC2626] dark:text-[#FCA5A5]'>{error}</p>
        </div>
      )}

      {!loading && !error && result && (
        <SimulationResultView
          result={result}
          adTitle={adTitle}
          adDescription={adDescription}
          initialReportView={savedReport}
          headerAction={headerAction}
        />
      )}
    </>
  );
}
