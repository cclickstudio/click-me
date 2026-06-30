// 어시스턴트 답변의 RAG 근거를 인용 칩으로 표시한다(P5). kb 칩 클릭 시 원문 일부를 펼친다.
'use client';

import { useState } from 'react';
import { api } from '@/lib/api';

type Citation = {
  kind: string;
  source: string;
  title?: string;
  source_url?: string; // web(Tavily) 인용 외부 링크
  trust?: string; // advisory 등
};

type ChunkState = { loading: boolean; text?: string; error?: string };

function fileLabel(source: string) {
  return source.replace(/\.md$/, '');
}

export default function CitationChips({
  citations,
  usedTools,
}: {
  citations?: Citation[];
  usedTools?: string[];
}) {
  const kb = (citations ?? []).filter(c => c.kind === 'kb');
  // 실측 근거 — 도메인 무관(매니지 live 도구·live kind 인용). 일반 내부 도구는 노이즈라 제외.
  const liveLabels = Array.from(
    new Set([
      ...(citations ?? []).filter(c => c.kind === 'live').map(c => c.source),
      ...(usedTools ?? []).filter(t => t.startsWith('live_')),
    ])
  ).map(t => t.replace('live_', '실측·').replace(/_/g, ' '));
  // 웹(Tavily) 인용 — advisory(참고). 외부 링크로 새 탭에 연다.
  const web = (citations ?? []).filter(c => c.kind === 'web');

  const [open, setOpen] = useState<number | null>(null);
  const [chunks, setChunks] = useState<Record<number, ChunkState>>({});

  if (kb.length === 0 && liveLabels.length === 0 && web.length === 0) return null;

  const toggle = async (i: number, c: Citation) => {
    if (open === i) {
      setOpen(null);
      return;
    }
    setOpen(i);
    if (!chunks[i]) {
      setChunks(p => ({ ...p, [i]: { loading: true } }));
      try {
        const r = await api.chat.kbChunk(c.source, c.title);
        setChunks(p => ({ ...p, [i]: { loading: false, text: r.chunk } }));
      } catch {
        setChunks(p => ({
          ...p,
          [i]: { loading: false, error: '원문을 불러오지 못했어요.' },
        }));
      }
    }
  };

  const active = open !== null ? kb[open] : null;
  const activeChunk = open !== null ? chunks[open] : undefined;

  return (
    <div className='px-1 mt-1.5 space-y-1.5'>
      <div className='flex flex-wrap items-center gap-1.5'>
        <span className='text-[10px] text-[#B0B8C1] dark:text-[#6B7280] shrink-0'>
          근거
        </span>
        {kb.map((c, i) => {
          const label = c.title || fileLabel(c.source);
          const isOpen = open === i;
          return (
            <button
              key={`kb-${i}`}
              type='button'
              onClick={() => toggle(i, c)}
              aria-expanded={isOpen}
              title={`${fileLabel(c.source)}${c.title ? ` › ${c.title}` : ''}`}
              className={`inline-flex items-center gap-1 max-w-[220px] rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
                isOpen
                  ? 'border-[#3182F6] bg-[#EBF3FF] text-[#3182F6] dark:bg-[#1E3A5F] dark:border-[#5B9DF9] dark:text-[#9CC4FF]'
                  : 'border-[#E5E8EB] bg-white text-[#4E5968] hover:border-[#3182F6] hover:text-[#3182F6] dark:bg-[#1A1F2B] dark:border-[#2D3748] dark:text-[#B0B8C1] dark:hover:border-[#5B9DF9]'
              }`}>
              <span aria-hidden>📄</span>
              <span className='truncate'>{label}</span>
            </button>
          );
        })}
        {liveLabels.map((t, i) => (
          <span
            key={`live-${i}`}
            className='inline-flex items-center gap-1 rounded-full border border-[#D7F5E3] bg-[#EAFBF1] px-2 py-0.5 text-[11px] text-[#15803D] dark:bg-[#0F2A1C] dark:border-[#1B4D33] dark:text-[#4ADE80]'>
            {t}
          </span>
        ))}
        {web.map((c, i) =>
          c.source_url ? (
            <a
              key={`web-${i}`}
              href={c.source_url}
              target='_blank'
              rel='noopener noreferrer'
              title={`${c.title || c.source_url} (웹 · 참고)`}
              className='inline-flex items-center gap-1 max-w-[220px] rounded-full border border-[#FCE7B5] bg-[#FFF8E6] px-2 py-0.5 text-[11px] text-[#B45309] hover:border-[#F59E0B] dark:bg-[#2A220F] dark:border-[#4D3D1B] dark:text-[#FBBF24]'>
              <span aria-hidden>🌐</span>
              <span className='truncate'>{c.title || '웹 출처'}</span>
            </a>
          ) : (
            <span
              key={`web-${i}`}
              className='inline-flex items-center gap-1 rounded-full border border-[#FCE7B5] bg-[#FFF8E6] px-2 py-0.5 text-[11px] text-[#B45309] dark:bg-[#2A220F] dark:border-[#4D3D1B] dark:text-[#FBBF24]'>
              <span aria-hidden>🌐</span>
              {c.title || '웹 출처'}
            </span>
          )
        )}
      </div>
      {active && (
        <div className='rounded-lg border border-[#E5E8EB] bg-[#F9FAFB] dark:bg-[#1A1F2B] dark:border-[#2D3748] p-2.5'>
          <p className='text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280] mb-1'>
            {fileLabel(active.source)}
            {active.title ? ` › ${active.title}` : ''}
          </p>
          {activeChunk?.loading && (
            <p className='text-[11px] text-[#B0B8C1] dark:text-[#6B7280]'>
              원문 불러오는 중…
            </p>
          )}
          {activeChunk?.error && (
            <p className='text-[11px] text-[#F04452]'>{activeChunk.error}</p>
          )}
          {activeChunk?.text && (
            <p className='text-[11px] leading-relaxed text-[#4E5968] dark:text-[#B0B8C1] whitespace-pre-wrap'>
              {activeChunk.text.length > 400
                ? `${activeChunk.text.slice(0, 400)}…`
                : activeChunk.text}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
