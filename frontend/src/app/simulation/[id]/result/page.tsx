'use client';
// 시뮬 결과 라우트 — 실행 직후(sessionStorage 전체 데이터) 또는 콜드/패널 진입(API db-result) 모두 처리.

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import AppLayout from '@/components/AppLayout';
import { SimulationResultView } from '@/components/simulator/SimulationResultView';
import { api } from '@/lib/api';
import { loadSimResult } from '@/lib/simResultStore';
import type { SimRunResult } from '@/lib/types';

export default function SimulationResultPage() {
  const { id } = useParams<{ id: string }>();
  const [result, setResult] = useState<SimRunResult | null>(null);
  const [adTitle, setAdTitle] = useState<string | undefined>();
  const [adDescription, setAdDescription] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    // 1) 방금 실행한 결과(전체 데이터)가 sessionStorage에 있으면 그대로 사용.
    const stored = loadSimResult(id);
    if (stored) {
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

  return (
    <AppLayout>
      {loading && (
        <div className='px-8 py-16 max-w-5xl mx-auto text-center'>
          <div className='inline-block w-8 h-8 border-4 border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] rounded-full animate-spin' />
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
        />
      )}
    </AppLayout>
  );
}
