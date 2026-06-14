'use client';

import { useState } from 'react';
import AppLayout from '@/components/AppLayout';

// ── 타입 ──────────────────────────────────────────────────────────────────────

type AdStrategy = 'benefit' | 'problem_solving' | 'social_proof' | 'emotional' | 'fomo';
type TemplateType = 'A' | 'B' | 'C';
type GenerationMode = 'create' | 'improve';
type AdSize = '1024x1024' | '1536x1024' | '1024x1536';

interface QualityCheckItem {
  passed: boolean;
  score: number;
  feedback: string;
}
interface QualityReport {
  typo_check: QualityCheckItem;
  duplicate_check: QualityCheckItem;
  cta_exists: QualityCheckItem;
  readability: QualityCheckItem;
  target_fit: QualityCheckItem;
  text_length: QualityCheckItem;
  brand_consistency: QualityCheckItem;
  overall_passed: boolean;
}
interface GeneratedAdVariant {
  variant_id: string;
  strategy: AdStrategy;
  template: TemplateType;
  image_s3_key: string;
  image_url: string;
  headline: string;
  body: string;
  cta: string;
  rationale: string;
  quality_report: QualityReport;
}
interface GenerateResult {
  generation_id: string;
  mode: GenerationMode;
  variants: GeneratedAdVariant[];
  created_at: string;
}

// ── 상수 ──────────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const STRATEGY_LABELS: Record<AdStrategy, string> = {
  benefit: '혜택 강조',
  problem_solving: '문제 해결',
  social_proof: '사회적 증거',
  emotional: '감성 접근',
  fomo: '긴급성(FOMO)',
};

const TEMPLATE_LABELS: Record<TemplateType, string> = {
  A: '템플릿 A — 제품 강조',
  B: '템플릿 B — 이벤트 강조',
  C: '템플릿 C — 브랜드 강조',
};

const QUALITY_LABELS: Record<keyof Omit<QualityReport, 'overall_passed'>, string> = {
  typo_check: '오타 검사',
  duplicate_check: '문구 중복',
  cta_exists: 'CTA 존재',
  readability: '가독성',
  target_fit: '타겟 적합성',
  text_length: '문구 길이',
  brand_consistency: '브랜드 일관성',
};

// ── 서브 컴포넌트 ─────────────────────────────────────────────────────────────

function QualityBadge({ item, label }: { item: QualityCheckItem; label: string }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-[#F2F4F6] dark:border-[#2D3748] last:border-0">
      <span
        className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold
          ${item.passed ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-500 dark:bg-red-900/30 dark:text-red-400'}`}
      >
        {item.passed ? '✓' : '✗'}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-[#333D4B] dark:text-[#E5E8EB]">{label}</span>
          <span className="text-[10px] text-[#8B95A1] dark:text-[#6B7280]">{Math.round(item.score * 100)}점</span>
        </div>
        {item.feedback && (
          <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280] mt-0.5">{item.feedback}</p>
        )}
      </div>
    </div>
  );
}

function AdVariantCard({
  variant,
  onImageClick,
}: {
  variant: GeneratedAdVariant;
  onImageClick: () => void;
}) {
  const [showQuality, setShowQuality] = useState(false);
  const qualityKeys = Object.keys(QUALITY_LABELS) as (keyof typeof QUALITY_LABELS)[];

  return (
    <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
      {/* 이미지 — 클릭 시 모달 */}
      <div
        className="relative bg-[#F2F4F6] dark:bg-[#252D3D] aspect-square cursor-pointer group"
        onClick={onImageClick}
      >
        <img
          src={variant.image_url}
          alt={`광고 ${variant.variant_id}`}
          className="w-full h-full object-cover transition-opacity group-hover:opacity-90"
        />
        {/* hover overlay */}
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="bg-black/50 rounded-full p-2.5">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="11" y1="8" x2="11" y2="14" /><line x1="8" y1="11" x2="14" y2="11" />
            </svg>
          </div>
        </div>
        <div className="absolute top-2 left-2 flex gap-1.5">
          <span className="text-[11px] font-semibold bg-white/90 dark:bg-[#1C2333]/90 text-[#333D4B] dark:text-[#E5E8EB] px-2 py-0.5 rounded-full">
            {variant.variant_id}안
          </span>
          <span className="text-[11px] bg-[#3182F6]/90 text-white px-2 py-0.5 rounded-full">
            {STRATEGY_LABELS[variant.strategy]}
          </span>
        </div>
        <div className="absolute top-2 right-2">
          <span className="text-[11px] bg-white/90 dark:bg-[#1C2333]/90 text-[#8B95A1] px-2 py-0.5 rounded-full">
            {TEMPLATE_LABELS[variant.template]}
          </span>
        </div>
      </div>

      {/* 광고 문구 */}
      <div className="p-4 space-y-2">
        <div>
          <p className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide mb-0.5">헤드라인</p>
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">{variant.headline}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide mb-0.5">본문</p>
          <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF]">{variant.body}</p>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide mb-0.5">CTA</p>
          <span className="inline-block text-xs font-medium bg-[#3182F6] text-white px-3 py-1 rounded-lg">{variant.cta}</span>
        </div>

        {/* 전략 근거 */}
        <div className="mt-3 pt-3 border-t border-[#F2F4F6] dark:border-[#2D3748]">
          <p className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide mb-1">전략 근거</p>
          <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed">{variant.rationale}</p>
        </div>

        {/* 품질 검증 */}
        <div className="mt-2 pt-2 border-t border-[#F2F4F6] dark:border-[#2D3748]">
          <button
            onClick={() => setShowQuality((v) => !v)}
            className="flex items-center justify-between w-full text-left"
          >
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-wide">품질 검증</span>
              <span
                className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full
                  ${variant.quality_report.overall_passed
                    ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
                    : 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400'}`}
              >
                {variant.quality_report.overall_passed ? '통과' : '주의'}
              </span>
            </div>
            <svg
              width="14" height="14"
              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              className={`text-[#8B95A1] transition-transform ${showQuality ? 'rotate-180' : ''}`}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          {showQuality && (
            <div className="mt-2">
              {qualityKeys.map((key) => (
                <QualityBadge key={key} item={variant.quality_report[key]} label={QUALITY_LABELS[key]} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AdDetailModal({
  variant,
  onClose,
}: {
  variant: GeneratedAdVariant;
  onClose: () => void;
}) {
  const qualityKeys = Object.keys(QUALITY_LABELS) as (keyof typeof QUALITY_LABELS)[];

  const [caption, setCaption] = useState(`${variant.headline}\n\n${variant.body}`);
  const [publishStatus, setPublishStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [publishResult, setPublishResult] = useState<{ post_id: string; permalink: string } | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);

  const handlePublish = async () => {
    setPublishStatus('loading');
    setPublishError(null);
    try {
      const res = await fetch(`${API_BASE}/api/generator/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_url: variant.image_url, caption }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setPublishResult(data);
      setPublishStatus('success');
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : '게시 중 오류가 발생했습니다.');
      setPublishStatus('error');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative bg-white dark:bg-[#1C2333] rounded-2xl w-full max-w-5xl max-h-[92vh] flex overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 닫기 버튼 */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 flex items-center justify-center transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        {/* 좌측: 이미지 */}
        <div className="w-[45%] flex-shrink-0 bg-[#0D1117] flex items-center justify-center">
          <img
            src={variant.image_url}
            alt={`광고 ${variant.variant_id}`}
            className="w-full h-full object-contain"
          />
        </div>

        {/* 우측: 상세 정보 */}
        <div className="flex-1 overflow-y-auto">
          {/* 헤더 */}
          <div className="sticky top-0 bg-white dark:bg-[#1C2333] border-b border-[#E5E8EB] dark:border-[#2D3748] px-6 py-4 flex items-center gap-2">
            <span className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">{variant.variant_id}안</span>
            <span className="text-[11px] bg-[#3182F6] text-white px-2 py-0.5 rounded-full">
              {STRATEGY_LABELS[variant.strategy]}
            </span>
            <span className="text-[11px] bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF] px-2 py-0.5 rounded-full">
              {TEMPLATE_LABELS[variant.template]}
            </span>
          </div>

          <div className="p-6 space-y-6">
            {/* 광고 카피 */}
            <section className="space-y-4">
              <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">광고 카피</h3>
              <div className="bg-[#F8F9FA] dark:bg-[#252D3D] rounded-xl p-4 space-y-3">
                <div>
                  <p className="text-[10px] font-semibold text-[#8B95A1] mb-1 uppercase tracking-wide">헤드라인</p>
                  <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] leading-snug">{variant.headline}</p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold text-[#8B95A1] mb-1 uppercase tracking-wide">본문</p>
                  <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed">{variant.body}</p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold text-[#8B95A1] mb-1 uppercase tracking-wide">CTA</p>
                  <span className="inline-block text-sm font-semibold bg-[#3182F6] text-white px-4 py-1.5 rounded-lg">{variant.cta}</span>
                </div>
              </div>
            </section>

            {/* 전략 근거 */}
            <section className="space-y-2">
              <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">전략 근거</h3>
              <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed">{variant.rationale}</p>
            </section>

            {/* 품질 검증 */}
            <section className="space-y-3">
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">품질 검증</h3>
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full
                    ${variant.quality_report.overall_passed
                      ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400'}`}
                >
                  {variant.quality_report.overall_passed ? '전체 통과' : '일부 주의'}
                </span>
              </div>
              <div className="bg-[#F8F9FA] dark:bg-[#252D3D] rounded-xl p-3">
                {qualityKeys.map((key) => (
                  <QualityBadge key={key} item={variant.quality_report[key]} label={QUALITY_LABELS[key]} />
                ))}
              </div>
            </section>

            {/* S3 키 */}
            <section className="space-y-1">
              <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">저장 경로</h3>
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] font-mono break-all">{variant.image_s3_key}</p>
            </section>

            {/* Instagram 게시 */}
            <section className="space-y-3 pt-2 border-t border-[#E5E8EB] dark:border-[#2D3748]">
              <div className="flex items-center gap-2">
                {/* Instagram 아이콘 */}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="flex-shrink-0">
                  <defs>
                    <linearGradient id="ig-grad" x1="0%" y1="100%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#f09433" />
                      <stop offset="25%" stopColor="#e6683c" />
                      <stop offset="50%" stopColor="#dc2743" />
                      <stop offset="75%" stopColor="#cc2366" />
                      <stop offset="100%" stopColor="#bc1888" />
                    </linearGradient>
                  </defs>
                  <rect x="2" y="2" width="20" height="20" rx="5" ry="5" stroke="url(#ig-grad)" strokeWidth="2" />
                  <circle cx="12" cy="12" r="4" stroke="url(#ig-grad)" strokeWidth="2" />
                  <circle cx="17.5" cy="6.5" r="1" fill="url(#ig-grad)" />
                </svg>
                <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">
                  Instagram 게시
                </h3>
              </div>

              {publishStatus === 'success' && publishResult ? (
                <div className="flex items-start gap-3 p-4 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800/30 rounded-xl">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-green-500 flex-shrink-0 mt-0.5">
                    <circle cx="12" cy="12" r="10" /><polyline points="9 12 11 14 15 10" />
                  </svg>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-green-700 dark:text-green-400">Instagram에 게시됐어요!</p>
                    <a
                      href={publishResult.permalink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-xs text-green-600 dark:text-green-500 hover:underline"
                    >
                      포스트 보기
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                        <polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
                      </svg>
                    </a>
                  </div>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1">
                      캡션 <span className="text-[#B0B8C1]">({caption.length} / 2,200)</span>
                    </label>
                    <textarea
                      value={caption}
                      onChange={(e) => setCaption(e.target.value)}
                      maxLength={2200}
                      rows={4}
                      placeholder="인스타그램 캡션을 입력하세요 (해시태그 포함)"
                      className="w-full px-3 py-2 text-sm rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-[#F8F9FA] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] focus:outline-none focus:border-[#3182F6] focus:ring-1 focus:ring-[#3182F6] transition-colors resize-none"
                    />
                  </div>

                  {publishStatus === 'error' && publishError && (
                    <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800/30 rounded-xl">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-red-500 flex-shrink-0 mt-0.5">
                        <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      <p className="text-xs text-red-600 dark:text-red-400">{publishError}</p>
                    </div>
                  )}

                  <button
                    onClick={handlePublish}
                    disabled={publishStatus === 'loading' || !caption.trim()}
                    className="w-full py-2.5 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                    style={{
                      background: publishStatus === 'loading'
                        ? '#aaa'
                        : 'linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)',
                    }}
                  >
                    {publishStatus === 'loading' ? (
                      <span className="flex items-center justify-center gap-2">
                        <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        게시 중...
                      </span>
                    ) : 'Instagram에 게시'}
                  </button>
                </>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

export default function Page() {
  const [mode, setMode] = useState<GenerationMode>('create');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalVariant, setModalVariant] = useState<GeneratedAdVariant | null>(null);

  // 생성모드 폼
  const [productName, setProductName] = useState('');
  const [description, setDescription] = useState('');
  const [target, setTarget] = useState('');
  const [objective, setObjective] = useState('conversion');
  const [brandColor, setBrandColor] = useState('');
  const [tone, setTone] = useState('');
  const [size, setSize] = useState<AdSize>('1024x1024');

  // 개선모드 폼
  const [existingS3Key, setExistingS3Key] = useState('');
  const [simulationSummary, setSimulationSummary] = useState('');
  const [fixRequests, setFixRequests] = useState('');
  const [improveProductName, setImproveProductName] = useState('');

  const handleSubmit = async () => {
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      const endpoint = mode === 'create' ? '/api/generator/generate' : '/api/generator/improve';
      const body =
        mode === 'create'
          ? { product_name: productName, description, target, objective, brand_color: brandColor || null, tone: tone || null, size }
          : { existing_ad_s3_key: existingS3Key, simulation_summary: simulationSummary, product_name: improveProductName || null, fix_requests: fixRequests || null, tone: tone || null, size };

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }

      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : '오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const isCreateValid = productName.trim() && description.trim() && target.trim();
  const isImproveValid = existingS3Key.trim() && simulationSummary.trim();
  const canSubmit = mode === 'create' ? isCreateValid : isImproveValid;

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        {/* 헤더 */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 제너레이터</h1>
          <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
            AI가 광고 전략을 수립하고 이미지 3종을 자동 생성합니다 · Meta / Instagram
          </p>
        </div>

        <div className="grid grid-cols-5 gap-5">
          {/* 입력 패널 */}
          <div className="col-span-2 space-y-4">
            {/* 모드 탭 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-1 flex transition-colors">
              {(['create', 'improve'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => { setMode(m); setResult(null); setError(null); }}
                  className={`flex-1 py-2 text-sm font-medium rounded-xl transition-colors
                    ${mode === m
                      ? 'bg-[#3182F6] text-white shadow-sm'
                      : 'text-[#8B95A1] dark:text-[#6B7280] hover:text-[#333D4B] dark:hover:text-[#E5E8EB]'}`}
                >
                  {m === 'create' ? '생성 모드' : '개선 모드'}
                </button>
              ))}
            </div>

            {/* 폼 */}
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors space-y-4">
              <div>
                <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                  {mode === 'create' ? '생성 설정' : '개선 설정'}
                </h2>
                <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">
                  {mode === 'create' ? '* 필수 항목' : '기존 광고 정보와 시뮬레이션 결과를 입력하세요'}
                </p>
              </div>

              {mode === 'create' ? (
                <>
                  <Field label="제품명 *">
                    <input value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="예: 스마트 텀블러 Pro" />
                  </Field>
                  <Field label="제품/서비스 설명 *">
                    <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="제품의 주요 특징, 기능, 차별점을 설명하세요" />
                  </Field>
                  <Field label="타겟 *">
                    <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="예: 20~35세 직장인, 건강에 관심 있는 여성" />
                  </Field>
                  <Field label="광고 목적 *">
                    <select value={objective} onChange={(e) => setObjective(e.target.value)}>
                      <option value="conversion">전환 (구매 유도)</option>
                      <option value="awareness">인지도 확대</option>
                      <option value="lead_gen">리드 수집</option>
                      <option value="promotion">프로모션/이벤트</option>
                    </select>
                  </Field>
                  <div className="border-t border-[#F2F4F6] dark:border-[#2D3748] pt-4">
                    <p className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280] mb-3">선택 옵션</p>
                    <div className="space-y-3">
                      <Field label="브랜드 컬러">
                        <input value={brandColor} onChange={(e) => setBrandColor(e.target.value)} placeholder="예: #3182F6" />
                      </Field>
                      <Field label="톤앤매너">
                        <input value={tone} onChange={(e) => setTone(e.target.value)} placeholder="예: 친근하고 활기찬" />
                      </Field>
                      <Field label="이미지 사이즈">
                        <select value={size} onChange={(e) => setSize(e.target.value as AdSize)}>
                          <option value="1024x1024">1:1 — 피드 기본 (1024×1024)</option>
                          <option value="1536x1024">3:2 — 가로형 (1536×1024)</option>
                          <option value="1024x1536">2:3 — 세로형 (1024×1536)</option>
                        </select>
                      </Field>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <Field label="제품명">
                    <input value={improveProductName} onChange={(e) => setImproveProductName(e.target.value)} placeholder="예: 스마트 텀블러 Pro (이미지 품질 향상)" />
                  </Field>
                  <Field label="기존 광고 S3 키 *">
                    <input value={existingS3Key} onChange={(e) => setExistingS3Key(e.target.value)} placeholder="예: ads/프로젝트ID/광고ID.png" />
                  </Field>
                  <Field label="시뮬레이션 결과 요약 *">
                    <textarea rows={4} value={simulationSummary} onChange={(e) => setSimulationSummary(e.target.value)} placeholder="구매 의향 분포, 페르소나 반응, 주요 문제점 등을 입력하세요" />
                  </Field>
                  <Field label="수정 요청사항">
                    <textarea rows={2} value={fixRequests} onChange={(e) => setFixRequests(e.target.value)} placeholder="추가로 수정하고 싶은 내용을 입력하세요" />
                  </Field>
                  <div className="border-t border-[#F2F4F6] dark:border-[#2D3748] pt-4">
                    <p className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280] mb-3">선택 옵션</p>
                    <div className="space-y-3">
                      <Field label="톤앤매너">
                        <input value={tone} onChange={(e) => setTone(e.target.value)} placeholder="예: 전문적이고 신뢰감 있는" />
                      </Field>
                      <Field label="이미지 사이즈">
                        <select value={size} onChange={(e) => setSize(e.target.value as AdSize)}>
                          <option value="1024x1024">1:1 — 피드 기본 (1024×1024)</option>
                          <option value="1536x1024">3:2 — 가로형 (1536×1024)</option>
                          <option value="1024x1536">2:3 — 세로형 (1024×1536)</option>
                        </select>
                      </Field>
                    </div>
                  </div>
                </>
              )}

              <button
                onClick={handleSubmit}
                disabled={!canSubmit || loading}
                className="w-full py-2.5 rounded-xl text-sm font-semibold transition-colors
                  bg-[#3182F6] text-white hover:bg-[#1B6AE4]
                  disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? '생성 중...' : '광고 생성'}
              </button>
            </div>
          </div>

          {/* 결과 패널 */}
          <div className="col-span-3">
            <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl p-6 transition-colors min-h-[500px]">
              <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">생성 결과</h2>
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">
                서로 다른 전략이 적용된 광고 3종이 생성됩니다 · 이미지를 클릭하면 자세히 볼 수 있습니다
              </p>

              {/* 로딩 */}
              {loading && (
                <div className="flex flex-col items-center justify-center py-16 gap-4">
                  <div className="w-10 h-10 border-4 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
                  <div className="text-center">
                    <p className="text-sm font-medium text-[#333D4B] dark:text-[#E5E8EB]">광고 이미지를 생성하는 중</p>
                    <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-1">AI가 전략을 수립하고 이미지를 생성합니다 · 최대 60초 소요</p>
                  </div>
                </div>
              )}

              {/* 에러 */}
              {!loading && error && (
                <div className="flex items-start gap-3 p-4 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800/30 rounded-xl">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-red-500 flex-shrink-0 mt-0.5">
                    <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                </div>
              )}

              {/* 결과 */}
              {!loading && result && (
                <div>
                  <div className="flex items-center gap-2 mb-4 pb-4 border-b border-[#F2F4F6] dark:border-[#2D3748]">
                    <span className="text-xs text-[#8B95A1] dark:text-[#6B7280]">생성 ID: {result.generation_id.slice(0, 8)}…</span>
                    <span className="text-[#D1D5DB]">·</span>
                    <span className="text-xs text-[#8B95A1] dark:text-[#6B7280]">{new Date(result.created_at).toLocaleString('ko-KR')}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    {result.variants.map((v) => (
                      <AdVariantCard
                        key={v.variant_id}
                        variant={v}
                        onImageClick={() => setModalVariant(v)}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* 빈 상태 */}
              {!loading && !result && !error && (
                <div className="flex flex-col items-center justify-center py-16 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl gap-2">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[#D1D5DB] dark:text-[#374151]">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <polyline points="21 15 16 10 5 21" />
                  </svg>
                  <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">좌측에서 정보를 입력하고 광고를 생성하세요</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 상세 모달 */}
      {modalVariant && (
        <AdDetailModal variant={modalVariant} onClose={() => setModalVariant(null)} />
      )}
    </AppLayout>
  );
}

// ── 공통 인풋 래퍼 ────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactElement }) {
  const inputClass =
    'w-full px-3 py-2 text-sm rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] ' +
    'bg-[#F8F9FA] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] ' +
    'placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] ' +
    'focus:outline-none focus:border-[#3182F6] focus:ring-1 focus:ring-[#3182F6] transition-colors';

  const child = children as React.ReactElement<{ className?: string }>;
  const styledChild = { ...child, props: { ...child.props, className: inputClass } };

  return (
    <div>
      <label className="block text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1">{label}</label>
      {styledChild}
    </div>
  );
}
