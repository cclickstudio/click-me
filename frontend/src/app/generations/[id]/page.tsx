'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import AppLayout from '@/components/AppLayout';
import { useProjects } from '@/components/ProjectContext';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Candidate = {
  candidate_id: string;
  idx: number;
  s3_key: string | null;
  image_url: string | null;
  copy: Record<string, string> | null;
  strategy: Record<string, unknown> | null;
  qa_passed: boolean | null;
  explanation: unknown;
};

type GenDetail = {
  generation_id: string;
  status: string;
  input: Record<string, unknown>;
  product_analysis: Record<string, unknown> | null;
  strategies: unknown[] | null;
  candidates: Candidate[];
  selected_candidate_id: string | null;
  created_at: string;
  error_message: string | null;
};

const statusStyle: Record<string, { bg: string; text: string; label: string }> = {
  completed: { bg: 'bg-emerald-50 dark:bg-emerald-900/20', text: 'text-emerald-600', label: '완료' },
  pending:   { bg: 'bg-yellow-50 dark:bg-yellow-900/20',   text: 'text-yellow-600',  label: '대기 중' },
  running:   { bg: 'bg-blue-50 dark:bg-blue-900/20',       text: 'text-blue-600',    label: '진행 중' },
  failed:    { bg: 'bg-red-50 dark:bg-red-900/20',         text: 'text-red-600',     label: '실패' },
};

const fmt = (iso: string) =>
  new Date(iso).toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-3 border-b border-[#F2F4F6] dark:border-[#252D3D] last:border-0">
      <span className="w-28 shrink-0 text-sm text-[#8B95A1] dark:text-[#6B7280]">{label}</span>
      <span className="text-sm text-[#191F28] dark:text-[#F2F4F6] flex-1">{value}</span>
    </div>
  );
}

function InputSection({ input }: { input: Record<string, unknown> }) {
  const fields: [string, string][] = [
    ['product_name', '상품명'],
    ['product_description', '상품 설명'],
    ['target_audience', '타겟 오디언스'],
    ['tone_and_manner', '광고 톤'],
    ['campaign_objective', '캠페인 목표'],
  ];
  return (
    <div className="space-y-0">
      {fields.map(([key, label]) =>
        input[key] ? (
          <InfoRow key={key} label={label} value={String(input[key])} />
        ) : null
      )}
    </div>
  );
}

function CandidateCard({ candidate, isSelected }: { candidate: Candidate; isSelected: boolean }) {
  const copy = candidate.copy;
  return (
    <div
      className={`rounded-2xl border overflow-hidden bg-white dark:bg-[#1C2333] ${
        isSelected
          ? 'border-[#3182F6] ring-2 ring-[#3182F6]/20'
          : 'border-[#E5E8EB] dark:border-[#2D3748]'
      }`}
    >
      {candidate.image_url ? (
        <div className="relative w-full aspect-square bg-[#F9FAFB] dark:bg-[#161B27]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={candidate.image_url}
            alt={`광고 후보 ${candidate.idx + 1}`}
            className="w-full h-full object-contain"
          />
          {isSelected && (
            <span className="absolute top-3 right-3 bg-[#3182F6] text-white text-xs font-semibold px-2.5 py-1 rounded-full">
              선택됨
            </span>
          )}
        </div>
      ) : (
        <div className="w-full aspect-square bg-[#F2F4F6] dark:bg-[#161B27] flex items-center justify-center">
          <span className="text-sm text-[#B0B8C1]">이미지 없음</span>
        </div>
      )}

      <div className="p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-[#8B95A1]">후보 {candidate.idx + 1}</span>
          {candidate.qa_passed !== null && (
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                candidate.qa_passed
                  ? 'bg-emerald-50 text-emerald-600'
                  : 'bg-red-50 text-red-500'
              }`}
            >
              {candidate.qa_passed ? 'QA 통과' : 'QA 미달'}
            </span>
          )}
        </div>
        {copy?.headline && (
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] leading-snug">
            {copy.headline}
          </p>
        )}
        {copy?.subcopy && (
          <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed">
            {copy.subcopy}
          </p>
        )}
        {copy?.cta && (
          <span className="inline-block mt-1 text-xs font-medium text-[#3182F6] border border-[#3182F6] rounded px-2 py-0.5">
            {copy.cta}
          </span>
        )}
      </div>
    </div>
  );
}

export default function GenerationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { projects, details } = useProjects();

  const [data, setData] = useState<GenDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // 인증 없이 접근 가능한 generator 엔드포인트 사용 (candidates + image_url 포함)
  useEffect(() => {
    fetch(`${API_BASE}/api/generator/generations/${id}`)
      .then(r => { if (!r.ok) throw new Error('not found'); return r.json(); })
      .then(setData)
      .catch(() => setError('제너레이터 내역을 불러올 수 없습니다.'))
      .finally(() => setLoading(false));
  }, [id]);

  // ProjectContext에서 프로젝트 이름 찾기
  const projectId = data?.input?.project_id as string | undefined;
  const project = projectId ? projects.find(p => p.id === projectId) : null;

  // 패널 details에서 해당 gen 항목 찾아 created_by_name 보완
  const genRow = projectId && details[projectId]
    ? details[projectId].gens.find(g => g.id === id)
    : null;

  const productName = data?.input?.product_name as string | undefined;
  const st = data
    ? (statusStyle[data.status] ?? { bg: 'bg-gray-50', text: 'text-gray-600', label: data.status })
    : null;

  return (
    <AppLayout>
      <div className="px-8 py-8 max-w-4xl mx-auto">
        <button
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-sm text-[#8B95A1] hover:text-[#3182F6] transition-colors mb-6"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          뒤로
        </button>

        {loading && <p className="text-sm text-[#8B95A1]">불러오는 중...</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}

        {data && (
          <>
            <div className="flex items-start justify-between mb-6">
              <div>
                {project && <p className="text-xs text-[#8B95A1] mb-1">{project.name}</p>}
                <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">
                  {productName ?? '제너레이터 상세'}
                </h1>
              </div>
              {st && (
                <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${st.bg} ${st.text}`}>
                  {st.label}
                </span>
              )}
            </div>

            {/* 기본 정보 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl px-6 py-2 mb-6">
              <InfoRow label="ID" value={<span className="font-mono text-xs">{data.generation_id}</span>} />
              {project && <InfoRow label="프로젝트" value={project.name} />}
              {genRow?.created_by_name && <InfoRow label="실행자" value={genRow.created_by_name} />}
              <InfoRow label="실행일시" value={fmt(data.created_at)} />
            </div>

            {/* 입력 정보 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl px-6 py-2 mb-6">
              <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] pt-4 pb-2">입력 정보</h2>
              {Object.keys(data.input).length > 0 ? (
                <InputSection input={data.input} />
              ) : (
                <p className="py-4 text-sm text-[#B0B8C1]">입력 정보가 없습니다.</p>
              )}
            </div>

            {/* 생성된 광고 후보 */}
            {data.candidates && data.candidates.length > 0 && (
              <div className="mb-6">
                <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
                  생성된 광고 후보 ({data.candidates.length}개)
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {data.candidates.map(c => (
                    <CandidateCard
                      key={c.candidate_id}
                      candidate={c}
                      isSelected={c.candidate_id === data.selected_candidate_id}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* 상품 분석 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 mb-6">
              <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">상품 분석</h2>
              {data.product_analysis ? (
                <pre className="text-xs bg-[#F9FAFB] dark:bg-[#161B27] rounded-xl p-4 overflow-x-auto text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed whitespace-pre-wrap">
                  {JSON.stringify(data.product_analysis, null, 2)}
                </pre>
              ) : (
                <div className="py-6 text-center text-sm text-[#B0B8C1] dark:text-[#4B5563]">
                  분석 데이터가 없습니다.
                </div>
              )}
            </div>

            {/* 광고 전략 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6">
              <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">
                광고 전략{data.strategies ? ` (${data.strategies.length}개)` : ''}
              </h2>
              {data.strategies && data.strategies.length > 0 ? (
                <pre className="text-xs bg-[#F9FAFB] dark:bg-[#161B27] rounded-xl p-4 overflow-x-auto text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed whitespace-pre-wrap">
                  {JSON.stringify(data.strategies, null, 2)}
                </pre>
              ) : (
                <div className="py-6 text-center text-sm text-[#B0B8C1] dark:text-[#4B5563]">
                  {data.status === 'completed' ? '전략 데이터가 없습니다.' : '생성이 아직 완료되지 않았습니다.'}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}
