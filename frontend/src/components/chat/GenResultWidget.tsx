// 채팅용 광고 생성 결과 위젯 — 후보 이미지 3장을 가로 스크롤로 보여주고 헤드라인·전략·QA·상세 링크 표시.
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Candidate = {
  candidate_id: string;
  idx: number;
  s3_key: string | null;
  image_url: string | null;
  copy: Record<string, string> | null;
  strategy: Record<string, unknown> | null;
  qa_passed: boolean | null;
  rank?: number | null;
  quality_score?: number | null;
  performance_summary?: string | null;
};
type GenDetail = {
  id: string;
  status: string;
  candidates: Candidate[];
};

// 후보 이미지 src — image_url(상대경로면 API_BASE 접두)을 우선, 없으면 s3_key로 온디맨드 조회.
function imgSrc(c: Candidate): string | null {
  if (c.image_url) {
    return c.image_url.startsWith('/') ? `${API_BASE}${c.image_url}` : c.image_url;
  }
  if (c.s3_key) {
    return `${API_BASE}/api/generator/image?key=${encodeURIComponent(c.s3_key)}`;
  }
  return null;
}

const CARD =
  'mt-2 w-full rounded-xl border border-line bg-card p-4';

export default function GenResultWidget({
  generationId,
  onSimulate,
}: {
  generationId: string;
  // F8 — 후보 카피·이미지로 시뮬 진입(제너→시뮬 루프). 없으면 버튼 미표시.
  onSimulate?: (adTitle: string, adContent: string, adImageUrl?: string) => void;
}) {
  const [detail, setDetail] = useState<GenDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.generator
      .detail(generationId)
      .then(d => {
        if (alive) setDetail(d as GenDetail);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [generationId]);

  if (loading) {
    return (
      <div className={CARD}>
        <div className='flex items-center gap-2 text-sm text-ink-tertiary'>
          <div className='w-3.5 h-3.5 border-2 border-line border-t-[#3182F6] dark:border-t-[#5B9DF9] rounded-full animate-spin' />
          광고 시안을 불러오는 중...
        </div>
      </div>
    );
  }
  if (!detail || !detail.candidates?.length) {
    return (
      <div className={CARD}>
        <p className='text-sm text-ink-tertiary'>광고 시안을 불러오지 못했어요.</p>
      </div>
    );
  }

  // 기대성과 순위(G7) 우선 정렬 — rank 없으면(구 데이터) idx 폴백.
  const cands = [...detail.candidates].sort(
    (a, b) => (a.rank ?? a.idx + 1) - (b.rank ?? b.idx + 1)
  );

  return (
    <div className={CARD}>
      <div className='flex items-center justify-between mb-3'>
        <span className='text-sm font-semibold text-ink'>
          🎨 광고 시안 {cands.length}개
        </span>
        <Link
          href={`/generations/${generationId}`}
          className='text-xs font-medium text-primary hover:underline'>
          상세 보기 →
        </Link>
      </div>
      <div className='flex gap-3 overflow-x-auto pb-1.5 -mx-1 px-1 snap-x'>
        {cands.map(c => {
          const src = imgSrc(c);
          const headline = c.copy?.headline;
          const stype = (c.strategy?.strategy_type as string) || '';
          return (
            <div
              key={c.candidate_id}
              className='shrink-0 w-44 snap-start rounded-lg border border-line overflow-hidden bg-white dark:bg-[#161B27]'>
              {src ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={src}
                  alt={`광고 후보 ${c.idx + 1}`}
                  className='w-44 h-44 object-cover bg-surface-1'
                />
              ) : (
                <div className='w-44 h-44 flex items-center justify-center bg-[#F2F4F6] dark:bg-[#161B27] text-xs text-ink-muted'>
                  이미지 없음
                </div>
              )}
              <div className='p-2.5 space-y-1'>
                <div className='flex items-center justify-between'>
                  <span className='text-[10px] font-semibold text-ink-tertiary'>
                    후보 {c.idx + 1}
                    {stype ? ` · ${stype}` : ''}
                  </span>
                  {c.qa_passed !== null && (
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                        c.qa_passed
                          ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400'
                          : 'bg-red-50 text-red-500 dark:bg-red-900/30 dark:text-red-400'
                      }`}>
                      {c.qa_passed ? 'QA 통과' : 'QA 미달'}
                    </span>
                  )}
                </div>
                {/* 기대성과 순위 배지(G7) — 1순위는 강조, 나머지는 순위 표시 */}
                {c.rank != null && (
                  <span
                    className={`inline-block text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${
                      c.rank === 1
                        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                        : 'bg-[#F2F4F6] text-ink-tertiary dark:bg-[#252D3D]'
                    }`}>
                    {c.rank === 1 ? '⭐ 추천 1순위' : `${c.rank}순위`}
                  </span>
                )}
                {headline && (
                  <p className='text-xs font-semibold text-ink leading-snug line-clamp-2'>
                    {headline}
                  </p>
                )}
                {c.performance_summary && (
                  <p className='text-[10px] text-ink-tertiary leading-snug'>
                    {c.performance_summary}
                  </p>
                )}
                {/* F8 — 이 후보 카피로 시뮬 진입(제너→시뮬 루프) */}
                {onSimulate && headline && (
                  <button
                    onClick={() =>
                      onSimulate(
                        headline,
                        [headline, c.copy?.body, c.copy?.cta]
                          .filter(Boolean)
                          .join('\n'),
                        imgSrc(c) ?? undefined
                      )
                    }
                    className='mt-1 w-full py-1.5 rounded-md border border-primary/30 text-primary text-[11px] font-semibold hover:bg-primary-subtle transition-colors'>
                    🧪 이 시안으로 시뮬
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
