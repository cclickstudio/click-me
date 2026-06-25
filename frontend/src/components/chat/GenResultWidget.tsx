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
  'mt-2 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-4';

export default function GenResultWidget({
  generationId,
}: {
  generationId: string;
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
        <div className='flex items-center gap-2 text-sm text-[#8B95A1]'>
          <div className='w-3.5 h-3.5 border-2 border-[#E5E8EB] dark:border-[#2D3748] border-t-[#3182F6] dark:border-t-[#5B9DF9] rounded-full animate-spin' />
          광고 시안을 불러오는 중...
        </div>
      </div>
    );
  }
  if (!detail || !detail.candidates?.length) {
    return (
      <div className={CARD}>
        <p className='text-sm text-[#8B95A1]'>광고 시안을 불러오지 못했어요.</p>
      </div>
    );
  }

  const cands = [...detail.candidates].sort((a, b) => a.idx - b.idx);

  return (
    <div className={CARD}>
      <div className='flex items-center justify-between mb-3'>
        <span className='text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]'>
          🎨 광고 시안 {cands.length}개
        </span>
        <Link
          href={`/generations/${detail.id}`}
          className='text-xs font-medium text-[#3182F6] hover:underline'>
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
              className='shrink-0 w-44 snap-start rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden bg-white dark:bg-[#161B27]'>
              {src ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={src}
                  alt={`광고 후보 ${c.idx + 1}`}
                  className='w-44 h-44 object-cover bg-[#F9FAFB] dark:bg-[#161B27]'
                />
              ) : (
                <div className='w-44 h-44 flex items-center justify-center bg-[#F2F4F6] dark:bg-[#161B27] text-xs text-[#B0B8C1]'>
                  이미지 없음
                </div>
              )}
              <div className='p-2.5 space-y-1'>
                <div className='flex items-center justify-between'>
                  <span className='text-[10px] font-semibold text-[#8B95A1]'>
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
                {headline && (
                  <p className='text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6] leading-snug line-clamp-2'>
                    {headline}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
