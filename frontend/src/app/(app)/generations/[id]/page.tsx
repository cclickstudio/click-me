'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import type { QualityReport } from '@/lib/types';
import { authedFetch } from '@/lib/api';
import { useProjects } from '@/components/ProjectContext';
import { useAuth } from '@/components/AuthProvider';
import ModeBadge from '@/components/ModeBadge';
import { formatKSTFull } from '@/lib/datetime';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type Candidate = {
  candidate_id: string;
  idx: number;
  s3_key: string | null;
  image_url: string | null;
  copy: Record<string, string> | null;
  strategy: Record<string, unknown> | null;
  qa_result: QualityReport | null;
  qa_passed: boolean | null;
  explanation: unknown;
};

type ProductAnalysis = {
  product_name?: string;
  core_values?: string[];
  pain_points?: string[];
  benefits?: string[];
  target_audience?: string;
  objective?: string;
  improvement_guidance?: string; // 개선모드: 이미지로 적용 어려운 개선점 가이드
};

type Strategy = {
  strategy?: string;
  strategy_description?: string;
  rationale?: string;
};

// AdStrategy enum → 한국어 라벨
const STRATEGY_LABELS: Record<string, string> = {
  benefit: '혜택 강조',
  problem_solving: '문제 해결',
  social_proof: '사회적 증거',
  fomo: '긴급성',
  emotional: '감성 접근',
};

type GenDetail = {
  generation_id: string;
  status: string;
  input: Record<string, unknown>;
  product_analysis: ProductAnalysis | null;
  strategies: Strategy[] | null;
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

const fmt = (iso: string) => formatKSTFull(iso);

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

// 플랫폼별 리레이아웃 미리보기 — ig_feed는 원본, 그 외는 온디맨드 렌더 엔드포인트
const PLATFORMS = [
  { key: 'ig_feed', label: 'IG 피드', aspect: 'aspect-square' },
  { key: 'ig_story', label: 'IG 스토리', aspect: 'aspect-[9/16]' },
  { key: 'fb_feed', label: 'Facebook', aspect: 'aspect-[1200/628]' },
  { key: 'linkedin', label: 'LinkedIn', aspect: 'aspect-[1200/627]' },
] as const;

// 후보 이미지 src — ig_feed는 원본(프록시), 그 외는 온디맨드 리레이아웃 렌더
function candidateImageSrc(candidate: Candidate, platform: string): string | null {
  const original = candidate.image_url
    ? candidate.image_url.startsWith('/')
      ? `${API_BASE}${candidate.image_url}`
      : candidate.image_url
    : null;
  return platform === 'ig_feed'
    ? original
    : `${API_BASE}/api/generator/candidates/${candidate.candidate_id}/render?platform=${platform}`;
}

function CandidateCard({
  candidate,
  isSelected,
  platform,
  aspect,
}: {
  candidate: Candidate;
  isSelected: boolean;
  platform: string;
  aspect: string;
}) {
  const copy = candidate.copy;
  const imgSrc = candidateImageSrc(candidate, platform);
  return (
    <div
      className={`rounded-2xl border overflow-hidden bg-white dark:bg-[#1C2333] ${
        isSelected
          ? 'border-[#3182F6] ring-2 ring-[#3182F6]/20'
          : 'border-[#E5E8EB] dark:border-[#2D3748]'
      }`}
    >
      {imgSrc ? (
        <div className={`relative w-full ${aspect} bg-[#F9FAFB] dark:bg-[#161B27]`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imgSrc}
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
        <div className={`w-full ${aspect} bg-[#F2F4F6] dark:bg-[#161B27] flex items-center justify-center`}>
          <span className="text-sm text-[#B0B8C1]">이미지 없음</span>
        </div>
      )}

      <div className="p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-[#8B95A1]">후보 {candidate.idx + 1}</span>
          {candidate.qa_passed !== null && (
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                !candidate.qa_passed
                  ? 'bg-red-50 text-red-500'
                  : (candidate.qa_result?.policy_warnings?.length ?? 0) > 0
                    ? 'bg-amber-50 text-amber-600'
                    : 'bg-emerald-50 text-emerald-600'
              }`}
              title={
                (candidate.qa_result?.policy_warnings?.length ?? 0) > 0
                  ? candidate.qa_result!.policy_warnings!.join('\n')
                  : undefined
              }
            >
              {!candidate.qa_passed
                ? 'QA 미달'
                : (candidate.qa_result?.policy_warnings?.length ?? 0) > 0
                  ? '정책 주의'
                  : 'QA 통과'}
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

function ChipList({ label, items }: { label: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex items-start gap-4 py-3 border-b border-[#F2F4F6] dark:border-[#252D3D] last:border-0">
      <span className="w-28 shrink-0 text-sm text-[#8B95A1] dark:text-[#6B7280]">{label}</span>
      <div className="flex flex-wrap gap-1.5 flex-1">
        {items.map((it, i) => (
          <span
            key={i}
            className="px-2.5 py-1 rounded-full text-xs bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]"
          >
            {it}
          </span>
        ))}
      </div>
    </div>
  );
}

function ProductAnalysisSection({ a }: { a: ProductAnalysis }) {
  return (
    <div className="space-y-0">
      {a.target_audience && <InfoRow label="타겟 고객" value={a.target_audience} />}
      {a.objective && <InfoRow label="캠페인 목표" value={a.objective} />}
      <ChipList label="핵심 가치" items={a.core_values} />
      <ChipList label="페인 포인트" items={a.pain_points} />
      <ChipList label="기대 효익" items={a.benefits} />
    </div>
  );
}

function StrategyCard({ s, idx }: { s: Strategy; idx: number }) {
  const label = s.strategy ? (STRATEGY_LABELS[s.strategy] ?? s.strategy) : `전략 ${idx + 1}`;
  return (
    <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-semibold text-[#8B95A1]">전략 {idx + 1}</span>
        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-[#EBF3FF] dark:bg-[#1E3A5F] text-[#3182F6]">
          {label}
        </span>
      </div>
      {s.strategy_description && (
        <p className="text-sm text-[#191F28] dark:text-[#F2F4F6] leading-relaxed">
          {s.strategy_description}
        </p>
      )}
      {s.rationale && (
        <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] leading-relaxed mt-2">
          💡 {s.rationale}
        </p>
      )}
    </div>
  );
}

function CarouselViewer({
  candidates,
  platform,
  aspect,
}: {
  candidates: Candidate[];
  platform: string;
  aspect: string;
}) {
  const slides = [...candidates].sort((a, b) => a.idx - b.idx);
  const [i, setI] = useState(0);
  const cur = Math.min(i, slides.length - 1);
  const c = slides[cur];
  const imgSrc = candidateImageSrc(c, platform);
  const role = (c.strategy as { strategy_description?: string } | null)?.strategy_description;
  return (
    <div className="max-w-sm">
      <div
        className={`relative w-full ${aspect} rounded-2xl overflow-hidden border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F9FAFB] dark:bg-[#161B27]`}
      >
        {imgSrc && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imgSrc} alt={`슬라이드 ${cur + 1}`} className="w-full h-full object-contain" />
        )}
        {cur > 0 && (
          <button
            onClick={() => setI(cur - 1)}
            className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70"
          >
            ‹
          </button>
        )}
        {cur < slides.length - 1 && (
          <button
            onClick={() => setI(cur + 1)}
            className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70"
          >
            ›
          </button>
        )}
      </div>
      <div className="mt-3 text-center">
        <p className="text-xs text-[#8B95A1] dark:text-[#6B7280]">
          슬라이드 {cur + 1} / {slides.length}
          {role ? ` · ${role}` : ''}
        </p>
        {c.copy?.headline && (
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mt-1">
            {c.copy.headline}
          </p>
        )}
        {c.copy?.body && (
          <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] mt-1">{c.copy.body}</p>
        )}
      </div>
      <div className="flex items-center justify-center gap-1.5 mt-3">
        {slides.map((s, idx) => (
          <button
            key={s.candidate_id}
            onClick={() => setI(idx)}
            className={`w-2 h-2 rounded-full transition-colors ${
              idx === cur ? 'bg-[#3182F6]' : 'bg-[#E5E8EB] dark:bg-[#2D3748]'
            }`}
          />
        ))}
      </div>
    </div>
  );
}

export default function GenerationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const { projects, details, refreshDetails } = useProjects();

  const [data, setData] = useState<GenDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [platform, setPlatform] = useState<string>('ig_feed');

  // generator 상세 — USE_MOCK=false면 org 스코프 인증 필요(머지 후) → 토큰 헤더 전달.
  useEffect(() => {
    authedFetch(`${API_BASE}/api/generator/generations/${id}`)
      .then(r => { if (!r.ok) throw new Error('not found'); return r.json(); })
      .then(setData)
      .catch(() => setError('제너레이터 내역을 불러올 수 없습니다.'))
      .finally(() => setLoading(false));
  }, [id]);

  // ProjectContext에서 프로젝트 이름 찾기
  const projectId = data?.input?.project_id as string | undefined;
  const project = projectId ? projects.find(p => p.id === projectId) : null;

  // 프로젝트 details 갱신 — 완료된(또는 조회하는) 생성물이 좌측 패널 목록에 반영되도록 재조회.
  useEffect(() => { if (projectId) refreshDetails(projectId); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 패널 details에서 해당 gen 항목 찾아 created_by_name 보완
  const genRow = projectId && details[projectId]
    ? details[projectId].gens.find(g => g.id === id)
    : null;

  // 휴지통(삭제됨) 여부 — projects 라우터가 아닌 generator 엔드포인트를 쓰므로 context로 판단
  const isDeleted = !!(projectId && details[projectId]?.trashed.some(t => t.kind === 'gen' && t.id === id));

  const productName = data?.input?.product_name as string | undefined;
  const isCarousel = (data?.input?.format as string | undefined) === 'carousel';
  const aspect = PLATFORMS.find(p => p.key === platform)?.aspect ?? 'aspect-square';
  const st = data
    ? (statusStyle[data.status] ?? { bg: 'bg-gray-50', text: 'text-gray-600', label: data.status })
    : null;

  const handleDelete = async () => {
    if (!confirm('이 제너레이터 내역을 삭제할까요?\n생성 후보·게시 이력이 함께 삭제됩니다.')) return;
    setDeleting(true);
    const res = await authedFetch(`${API_BASE}/api/projects/generations/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) { setDeleting(false); alert('삭제에 실패했습니다.'); return; }
    if (projectId) await refreshDetails(projectId); // 패널 카운트 실시간 반영
    router.push(projectId ? `/projects/${projectId}` : '/dashboard');
  };

  const handleRestore = async () => {
    setRestoring(true);
    const res = await authedFetch(`${API_BASE}/api/projects/generations/${id}/restore`, {
      method: 'POST',
    });
    setRestoring(false);
    if (!res.ok) { alert('복원에 실패했습니다.'); return; }
    if (projectId) await refreshDetails(projectId); // 휴지통 목록 갱신 → 배지 해제
  };

  return (
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
                <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6] flex items-center gap-2">
                  <ModeBadge
                    mode={data.input?.mode as string | undefined}
                    format={data.input?.format as string | undefined}
                  />
                  {productName ?? '제너레이터 상세'}
                  {isDeleted && (
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 dark:bg-red-900/20 text-red-600">삭제됨</span>
                  )}
                </h1>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {st && (
                  <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${st.bg} ${st.text}`}>
                    {st.label}
                  </span>
                )}
                {isDeleted ? (
                  <button
                    onClick={handleRestore}
                    disabled={restoring}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-[#3182F6] border border-[#3182F6]/30 hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] transition-colors disabled:opacity-40"
                  >
                    {restoring ? '복원 중...' : '복원'}
                  </button>
                ) : (
                  <button
                    onClick={handleDelete}
                    disabled={deleting}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-red-500 border border-red-200 dark:border-red-900/40 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M9 6V4h6v2" />
                    </svg>
                    {deleting ? '삭제 중...' : '삭제'}
                  </button>
                )}
              </div>
            </div>

            {/* 기본 정보 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl px-6 py-2 mb-6">
              {isAdmin && <InfoRow label="ID" value={<span className="font-mono text-xs">{data.generation_id}</span>} />}
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
                <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
                  <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                    {isCarousel
                      ? `카드뉴스 (${data.candidates.length}장)`
                      : `생성된 광고 후보 (${data.candidates.length}개)`}
                  </h2>
                  {/* 플랫폼별 리레이아웃 미리보기 토글 */}
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {PLATFORMS.map(p => (
                      <button
                        key={p.key}
                        onClick={() => setPlatform(p.key)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                          platform === p.key
                            ? 'bg-[#3182F6] text-white'
                            : 'bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF] hover:text-[#3182F6]'
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
                {isCarousel ? (
                  <CarouselViewer candidates={data.candidates} platform={platform} aspect={aspect} />
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {data.candidates.map(c => (
                      <CandidateCard
                        key={c.candidate_id}
                        candidate={c}
                        isSelected={c.candidate_id === data.selected_candidate_id}
                        platform={platform}
                        aspect={aspect}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 개선 적용 가이드 (개선모드) */}
            {data.product_analysis?.improvement_guidance && (
              <div className="bg-[#FFF8EF] dark:bg-[#2A2114] border border-[#FCD9A8] dark:border-[#5A4420] rounded-2xl p-6 mb-6">
                <h2 className="text-base font-semibold text-[#B45309] dark:text-[#F0A84B] mb-3 flex items-center gap-2">
                  💡 개선 적용 가이드
                </h2>
                <p className="text-sm text-[#7A5418] dark:text-[#E8C896] leading-relaxed whitespace-pre-wrap">
                  {data.product_analysis.improvement_guidance}
                </p>
              </div>
            )}

            {/* 상품 분석 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 mb-6">
              <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-4">상품 분석</h2>
              {data.product_analysis ? (
                <ProductAnalysisSection a={data.product_analysis} />
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
                <div className="space-y-3">
                  {data.strategies.map((s, i) => (
                    <StrategyCard key={i} s={s} idx={i} />
                  ))}
                </div>
              ) : (
                <div className="py-6 text-center text-sm text-[#B0B8C1] dark:text-[#4B5563]">
                  {data.status === 'completed' ? '전략 데이터가 없습니다.' : '생성이 아직 완료되지 않았습니다.'}
                </div>
              )}
            </div>
          </>
        )}
      </div>
  );
}
