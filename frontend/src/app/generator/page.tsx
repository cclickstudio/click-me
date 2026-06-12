'use client';

import { useState } from 'react';
import AppLayout from '@/components/AppLayout';

// ── 타입 ──────────────────────────────────────────────────────────────────────

type AdStrategy = 'benefit' | 'problem_solving' | 'social_proof' | 'emotional' | 'urgency';
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
  urgency: '긴급성(FOMO)',
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
          <p className="text-[11px] text-[#8B95A1] dark:text-[#6B7280] mt-0.5 truncate">{item.feedback}</p>
        )}
      </div>
    </div>
  );
}

function AdVariantCard({ variant }: { variant: GeneratedAdVariant }) {
  const [showQuality, setShowQuality] = useState(false);
  const qualityKeys = Object.keys(QUALITY_LABELS) as (keyof typeof QUALITY_LABELS)[];

  return (
    <div className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden">
      {/* 이미지 */}
      <div className="relative bg-[#F2F4F6] dark:bg-[#252D3D] aspect-square">
        <img
          src={variant.image_url}
          alt={`광고 ${variant.variant_id}`}
          className="w-full h-full object-cover"
        />
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
                <QualityBadge
                  key={key}
                  item={variant.quality_report[key]}
                  label={QUALITY_LABELS[key]}
                />
              ))}
            </div>
          )}
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

  const handleSubmit = async () => {
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      const endpoint = mode === 'create' ? '/api/generator/generate' : '/api/generator/improve';
      const body =
        mode === 'create'
          ? { product_name: productName, description, target, objective, brand_color: brandColor || null, tone: tone || null, size }
          : { existing_ad_s3_key: existingS3Key, simulation_summary: simulationSummary, fix_requests: fixRequests || null, tone: tone || null, size };

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
            AI가 광고 전략을 수립하고 이미지 2종을 자동 생성합니다 · Meta / Instagram
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
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">서로 다른 전략이 적용된 광고 2종이 생성됩니다</p>

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
                  <div className="grid grid-cols-2 gap-4">
                    {result.variants.map((v) => (
                      <AdVariantCard key={v.variant_id} variant={v} />
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
