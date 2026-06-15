"use client";

import { useEffect, useRef, useState } from "react";
import AppLayout from "@/components/AppLayout";
import { api } from "@/lib/api";
import type {
  CampaignResult,
  GenerationDetail,
  GeneratorCandidate,
  PublishResult,
  SSEProgressEvent,
} from "@/lib/types";

// ── 공통 타입 ────────────────────────────────────────────────────────────────

type Step = "input" | "generating" | "candidates" | "selected";
type PageMode = "graph" | "pipeline";

// pipeline 전용 타입
type PipelineAdStrategy = "benefit" | "problem_solving" | "social_proof" | "emotional" | "fomo";
type PipelineTemplateType = "A" | "B" | "C";
type PipelineMode = "create" | "improve";
type AdSize = "1024x1024" | "1536x1024" | "1024x1536";

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
  strategy: PipelineAdStrategy;
  template: PipelineTemplateType;
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
  mode: PipelineMode;
  variants: GeneratedAdVariant[];
  created_at: string;
}

// ── 공통 상수 ────────────────────────────────────────────────────────────────

const OBJECTIVES = [
  { value: "awareness", label: "브랜드 인지" },
  { value: "conversion", label: "구매 전환" },
  { value: "lead_gen", label: "리드 수집" },
  { value: "app_install", label: "앱 설치" },
  { value: "retention", label: "재구매 유도" },
  { value: "product_launch", label: "신제품 런칭" },
  { value: "promotion", label: "프로모션 반응" },
];

const META_OBJECTIVES = [
  { value: "OUTCOME_TRAFFIC", label: "트래픽" },
  { value: "OUTCOME_AWARENESS", label: "인지도" },
  { value: "OUTCOME_ENGAGEMENT", label: "참여" },
  { value: "OUTCOME_LEADS", label: "리드" },
  { value: "OUTCOME_SALES", label: "판매" },
  { value: "OUTCOME_APP_PROMOTION", label: "앱 홍보" },
];

const SIZES = [
  { label: "1:1 (1080×1080)", width: 1080, height: 1080 },
  { label: "가로 (1920×1080)", width: 1920, height: 1080 },
  { label: "세로 (1080×1920)", width: 1080, height: 1920 },
];

const STAGES = [
  { key: "product_analysis", label: "상품 분석" },
  { key: "strategy", label: "광고 전략 생성" },
  { key: "template", label: "템플릿 선택" },
  { key: "candidates", label: "광고 후보 3종 생성" },
  { key: "qa", label: "품질 검증" },
  { key: "explain", label: "생성 이유 작성" },
];

const QA_LABELS: Record<string, string> = {
  cta_presence: "CTA 존재",
  copy_length: "문구 길이",
  duplication: "문구 중복",
  typo: "오타 검사",
  readability: "가독성",
  target_fit: "타겟 적합성",
  brand_consistency: "브랜드 일관성",
};

// pipeline 전용 상수
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STRATEGY_LABELS: Record<PipelineAdStrategy, string> = {
  benefit: "혜택 강조",
  problem_solving: "문제 해결",
  social_proof: "사회적 증거",
  emotional: "감성 접근",
  fomo: "긴급성(FOMO)",
};

const TEMPLATE_LABELS: Record<PipelineTemplateType, string> = {
  A: "템플릿 A — 제품 강조",
  B: "템플릿 B — 이벤트 강조",
  C: "템플릿 C — 브랜드 강조",
};

const QUALITY_LABELS: Record<keyof Omit<QualityReport, "overall_passed">, string> = {
  typo_check: "오타 검사",
  duplicate_check: "문구 중복",
  cta_exists: "CTA 존재",
  readability: "가독성",
  target_fit: "타겟 적합성",
  text_length: "문구 길이",
  brand_consistency: "브랜드 일관성",
};

// yohan 스타일 상수
const inputCls =
  "w-full px-3 py-2.5 text-sm rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] transition-colors";
const labelCls = "block text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5";
const cardCls =
  "bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl transition-colors";

// ── Pipeline 전용 서브 컴포넌트 ───────────────────────────────────────────────

function QualityBadge({ item, label }: { item: QualityCheckItem; label: string }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-[#F2F4F6] dark:border-[#2D3748] last:border-0">
      <span
        className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold
          ${item.passed ? "bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400" : "bg-red-100 text-red-500 dark:bg-red-900/30 dark:text-red-400"}`}
      >
        {item.passed ? "✓" : "✗"}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-[#333D4B] dark:text-[#E5E8EB]">{label}</span>
          <span className="text-[10px] text-[#8B95A1] dark:text-[#6B7280]">
            {Math.round(item.score * 100)}점
          </span>
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
  return (
    <div
      className="bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl overflow-hidden cursor-pointer group flex"
      onClick={onImageClick}
    >
      <div className="relative bg-[#F2F4F6] dark:bg-[#252D3D] w-52 flex-shrink-0 aspect-square">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={variant.image_url}
          alt={`광고 ${variant.variant_id}`}
          className="w-full h-full object-cover transition-opacity group-hover:opacity-90"
        />
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="bg-black/50 rounded-full p-2.5">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="11" y1="8" x2="11" y2="14" />
              <line x1="8" y1="11" x2="14" y2="11" />
            </svg>
          </div>
        </div>
        <div className="absolute top-2 left-2">
          <span className="text-[11px] font-semibold bg-black/50 text-white px-2 py-0.5 rounded-full">
            {variant.variant_id}안
          </span>
        </div>
      </div>
      <div className="flex-1 p-5 flex flex-col justify-between min-w-0">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] bg-[#3182F6] text-white px-2 py-0.5 rounded-full">
              {STRATEGY_LABELS[variant.strategy]}
            </span>
            <span className="text-[11px] bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1] dark:text-[#6B7280] px-2 py-0.5 rounded-full">
              {TEMPLATE_LABELS[variant.template]}
            </span>
          </div>
          <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] leading-snug line-clamp-2">
            {variant.headline}
          </p>
          <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] leading-relaxed line-clamp-2">
            {variant.body}
          </p>
        </div>
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#F2F4F6] dark:border-[#2D3748]">
          <span className="text-xs font-semibold text-[#4E5968] dark:text-[#9CA3AF] bg-[#F8F9FA] dark:bg-[#252D3D] px-3 py-1 rounded-lg">
            {variant.cta}
          </span>
          <span className="text-xs text-[#3182F6] font-medium">자세히 보기 →</span>
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
  const [publishStatus, setPublishStatus] = useState<"idle" | "loading" | "success" | "error">(
    "idle",
  );
  const [publishResult, setPublishResult] = useState<{
    post_id: string;
    permalink: string;
  } | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);

  const handlePublish = async () => {
    setPublishStatus("loading");
    setPublishError(null);
    try {
      const res = await fetch(`${API_BASE}/api/generator/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_url: variant.image_url, caption }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setPublishResult(data);
      setPublishStatus("success");
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : "게시 중 오류가 발생했습니다.");
      setPublishStatus("error");
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
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 flex items-center justify-center transition-colors"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="white"
            strokeWidth="2.5"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <div className="w-[45%] flex-shrink-0 bg-[#0D1117] flex items-center justify-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={variant.image_url}
            alt={`광고 ${variant.variant_id}`}
            className="w-full h-full object-contain"
          />
        </div>
        <div className="flex-1 overflow-y-auto">
          <div className="sticky top-0 bg-white dark:bg-[#1C2333] border-b border-[#E5E8EB] dark:border-[#2D3748] px-6 py-4 flex items-center gap-2">
            <span className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">
              {variant.variant_id}안
            </span>
            <span className="text-[11px] bg-[#3182F6] text-white px-2 py-0.5 rounded-full">
              {STRATEGY_LABELS[variant.strategy]}
            </span>
            <span className="text-[11px] bg-[#F2F4F6] dark:bg-[#252D3D] text-[#4E5968] dark:text-[#9CA3AF] px-2 py-0.5 rounded-full">
              {TEMPLATE_LABELS[variant.template]}
            </span>
          </div>
          <div className="p-6 space-y-6">
            <section className="space-y-4">
              <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">
                광고 카피
              </h3>
              <div className="bg-[#F8F9FA] dark:bg-[#252D3D] rounded-xl p-4 space-y-3">
                <div>
                  <p className="text-[10px] font-semibold text-[#8B95A1] mb-1 uppercase tracking-wide">
                    헤드라인
                  </p>
                  <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] leading-snug">
                    {variant.headline}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold text-[#8B95A1] mb-1 uppercase tracking-wide">
                    본문
                  </p>
                  <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed">
                    {variant.body}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold text-[#8B95A1] mb-1 uppercase tracking-wide">
                    CTA
                  </p>
                  <span className="inline-block text-sm font-semibold bg-[#3182F6] text-white px-4 py-1.5 rounded-lg">
                    {variant.cta}
                  </span>
                </div>
              </div>
            </section>
            <section className="space-y-2">
              <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">
                전략 근거
              </h3>
              <p className="text-sm text-[#4E5968] dark:text-[#9CA3AF] leading-relaxed">
                {variant.rationale}
              </p>
            </section>
            <section className="space-y-3">
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">
                  품질 검증
                </h3>
                <span
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                    variant.quality_report.overall_passed
                      ? "bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400"
                  }`}
                >
                  {variant.quality_report.overall_passed ? "전체 통과" : "일부 주의"}
                </span>
              </div>
              <div className="bg-[#F8F9FA] dark:bg-[#252D3D] rounded-xl p-3">
                {qualityKeys.map((key) => (
                  <QualityBadge
                    key={key}
                    item={variant.quality_report[key]}
                    label={QUALITY_LABELS[key]}
                  />
                ))}
              </div>
            </section>
            <section className="space-y-1">
              <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">
                저장 경로
              </h3>
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563] font-mono break-all">
                {variant.image_s3_key}
              </p>
            </section>
            <section className="space-y-3 pt-2 border-t border-[#E5E8EB] dark:border-[#2D3748]">
              <h3 className="text-xs font-bold text-[#8B95A1] dark:text-[#6B7280] uppercase tracking-widest">
                Instagram 게시
              </h3>
              {publishStatus === "success" && publishResult ? (
                <div className="flex items-start gap-3 p-4 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800/30 rounded-xl">
                  <p className="text-sm font-medium text-green-700 dark:text-green-400">
                    Instagram에 게시됐어요!
                  </p>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1">
                      캡션 ({caption.length} / 2,200)
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
                  {publishStatus === "error" && publishError && (
                    <p className="text-xs text-red-600 dark:text-red-400">{publishError}</p>
                  )}
                  <button
                    onClick={handlePublish}
                    disabled={publishStatus === "loading" || !caption.trim()}
                    className="w-full py-2.5 rounded-xl text-sm font-semibold text-white bg-[#3182F6] hover:bg-[#1B64DA] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {publishStatus === "loading" ? "게시 중..." : "Instagram에 게시"}
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

// ── 빠른 생성 (파이프라인 모드) ────────────────────────────────────────────────

function PipelinePage() {
  const [mode, setMode] = useState<PipelineMode>("create");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modalVariant, setModalVariant] = useState<GeneratedAdVariant | null>(null);

  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [target, setTarget] = useState("");
  const [objective, setObjective] = useState("conversion");
  const [brandColor, setBrandColor] = useState("");
  const [tone, setTone] = useState("");
  const [size, setSize] = useState<AdSize>("1024x1024");

  const [existingS3Key, setExistingS3Key] = useState("");
  const [simulationSummary, setSimulationSummary] = useState("");
  const [fixRequests, setFixRequests] = useState("");
  const [improveProductName, setImproveProductName] = useState("");

  const handleSubmit = async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const endpoint =
        mode === "create" ? "/api/generator/generate" : "/api/generator/improve";
      const body =
        mode === "create"
          ? {
              product_name: productName,
              description,
              target,
              objective,
              brand_color: brandColor || null,
              tone: tone || null,
              size,
            }
          : {
              existing_ad_s3_key: existingS3Key,
              simulation_summary: simulationSummary,
              product_name: improveProductName || null,
              fix_requests: fixRequests || null,
              tone: tone || null,
              size,
            };
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const isCreateValid = productName.trim() && description.trim() && target.trim();
  const isImproveValid = existingS3Key.trim() && simulationSummary.trim();
  const canSubmit = mode === "create" ? isCreateValid : isImproveValid;

  return (
    <div className="grid grid-cols-5 gap-5">
      <div className="col-span-2 space-y-4">
        <div
          className={`${cardCls} p-1 flex`}
        >
          {(["create", "improve"] as const).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setResult(null);
                setError(null);
              }}
              className={`flex-1 py-2 text-sm font-medium rounded-xl transition-colors
                ${mode === m ? "bg-[#3182F6] text-white shadow-sm" : "text-[#8B95A1] dark:text-[#6B7280] hover:text-[#333D4B] dark:hover:text-[#E5E8EB]"}`}
            >
              {m === "create" ? "생성 모드" : "개선 모드"}
            </button>
          ))}
        </div>

        <div className={`${cardCls} p-6 space-y-4`}>
          <div>
            <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
              {mode === "create" ? "생성 설정" : "개선 설정"}
            </h2>
            <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">
              {mode === "create" ? "* 필수 항목" : "기존 광고 정보와 시뮬레이션 결과를 입력하세요"}
            </p>
          </div>

          {mode === "create" ? (
            <>
              <PipelineField label="제품명 *">
                <input
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                  placeholder="예: 스마트 텀블러 Pro"
                />
              </PipelineField>
              <PipelineField label="제품/서비스 설명 *">
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="제품의 주요 특징, 기능, 차별점을 설명하세요"
                />
              </PipelineField>
              <PipelineField label="타겟 *">
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder="예: 20~35세 직장인, 건강에 관심 있는 여성"
                />
              </PipelineField>
              <PipelineField label="광고 목적 *">
                <select value={objective} onChange={(e) => setObjective(e.target.value)}>
                  <option value="conversion">전환 (구매 유도)</option>
                  <option value="awareness">인지도 확대</option>
                  <option value="lead_gen">리드 수집</option>
                  <option value="promotion">프로모션/이벤트</option>
                </select>
              </PipelineField>
              <div className="border-t border-[#F2F4F6] dark:border-[#2D3748] pt-4 space-y-3">
                <p className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280]">선택 옵션</p>
                <PipelineField label="브랜드 컬러">
                  <input
                    value={brandColor}
                    onChange={(e) => setBrandColor(e.target.value)}
                    placeholder="예: #3182F6"
                  />
                </PipelineField>
                <PipelineField label="톤앤매너">
                  <input
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    placeholder="예: 친근하고 활기찬"
                  />
                </PipelineField>
                <PipelineField label="이미지 사이즈">
                  <select value={size} onChange={(e) => setSize(e.target.value as AdSize)}>
                    <option value="1024x1024">1:1 — 피드 기본 (1024×1024)</option>
                    <option value="1536x1024">3:2 — 가로형 (1536×1024)</option>
                    <option value="1024x1536">2:3 — 세로형 (1024×1536)</option>
                  </select>
                </PipelineField>
              </div>
            </>
          ) : (
            <>
              <PipelineField label="제품명">
                <input
                  value={improveProductName}
                  onChange={(e) => setImproveProductName(e.target.value)}
                  placeholder="예: 스마트 텀블러 Pro"
                />
              </PipelineField>
              <PipelineField label="기존 광고 S3 키 *">
                <input
                  value={existingS3Key}
                  onChange={(e) => setExistingS3Key(e.target.value)}
                  placeholder="예: ads/프로젝트ID/광고ID.png"
                />
              </PipelineField>
              <PipelineField label="시뮬레이션 결과 요약 *">
                <textarea
                  rows={4}
                  value={simulationSummary}
                  onChange={(e) => setSimulationSummary(e.target.value)}
                  placeholder="구매 의향 분포, 페르소나 반응, 주요 문제점 등을 입력하세요"
                />
              </PipelineField>
              <PipelineField label="수정 요청사항">
                <textarea
                  rows={2}
                  value={fixRequests}
                  onChange={(e) => setFixRequests(e.target.value)}
                  placeholder="추가로 수정하고 싶은 내용을 입력하세요"
                />
              </PipelineField>
              <div className="border-t border-[#F2F4F6] dark:border-[#2D3748] pt-4 space-y-3">
                <p className="text-xs font-medium text-[#8B95A1] dark:text-[#6B7280]">선택 옵션</p>
                <PipelineField label="톤앤매너">
                  <input
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    placeholder="예: 전문적이고 신뢰감 있는"
                  />
                </PipelineField>
                <PipelineField label="이미지 사이즈">
                  <select value={size} onChange={(e) => setSize(e.target.value as AdSize)}>
                    <option value="1024x1024">1:1 — 피드 기본 (1024×1024)</option>
                    <option value="1536x1024">3:2 — 가로형 (1536×1024)</option>
                    <option value="1024x1536">2:3 — 세로형 (1024×1536)</option>
                  </select>
                </PipelineField>
              </div>
            </>
          )}

          <button
            onClick={handleSubmit}
            disabled={!canSubmit || loading}
            className="w-full py-2.5 rounded-xl text-sm font-semibold transition-colors bg-[#3182F6] text-white hover:bg-[#1B6AE4] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? "생성 중..." : "광고 생성"}
          </button>
        </div>
      </div>

      <div className="col-span-3">
        <div className={`${cardCls} p-6 min-h-[500px]`}>
          <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">생성 결과</h2>
          <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">
            서로 다른 전략이 적용된 광고 3종 · 이미지를 클릭하면 자세히 볼 수 있습니다
          </p>

          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-4">
              <div className="w-10 h-10 border-4 border-[#3182F6] border-t-transparent rounded-full animate-spin" />
              <div className="text-center">
                <p className="text-sm font-medium text-[#333D4B] dark:text-[#E5E8EB]">
                  광고 이미지를 생성하는 중
                </p>
                <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-1">
                  AI가 전략을 수립하고 이미지를 생성합니다 · 최대 60초 소요
                </p>
              </div>
            </div>
          )}

          {!loading && error && (
            <p className="text-sm text-red-600 dark:text-red-400 p-4 bg-red-50 dark:bg-red-900/10 rounded-xl">
              {error}
            </p>
          )}

          {!loading && result && (
            <div>
              <div className="flex items-center gap-2 mb-4 pb-4 border-b border-[#F2F4F6] dark:border-[#2D3748]">
                <span className="text-xs text-[#8B95A1] dark:text-[#6B7280]">
                  생성 ID: {result.generation_id.slice(0, 8)}…
                </span>
                <span className="text-[#D1D5DB]">·</span>
                <span className="text-xs text-[#8B95A1] dark:text-[#6B7280]">
                  {new Date(result.created_at).toLocaleString("ko-KR")}
                </span>
              </div>
              <div className="flex flex-col gap-3">
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

          {!loading && !result && !error && (
            <div className="flex flex-col items-center justify-center py-16 border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl gap-2">
              <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">
                좌측에서 정보를 입력하고 광고를 생성하세요
              </p>
            </div>
          )}
        </div>
      </div>

      {modalVariant && (
        <AdDetailModal variant={modalVariant} onClose={() => setModalVariant(null)} />
      )}
    </div>
  );
}

// ── 메인 페이지 (전체 생성 — graph/SSE 멀티스텝) ────────────────────────────

export default function GeneratorPage() {
  const [pageMode, setPageMode] = useState<PageMode>("graph");
  const [step, setStep] = useState<Step>("input");

  const [clientId, setClientId] = useState<string>("");
  const [logoS3Key, setLogoS3Key] = useState<string>("");
  const [logoPreviewUrl, setLogoPreviewUrl] = useState<string>("");
  const [logoUploading, setLogoUploading] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const logoInputRef = useRef<HTMLInputElement>(null);

  const [productName, setProductName] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [objective, setObjective] = useState("conversion");
  const [showOptional, setShowOptional] = useState(false);
  const [brandColor, setBrandColor] = useState("");
  const [toneAndManner, setToneAndManner] = useState("");
  const [sizeIdx, setSizeIdx] = useState(0);

  const [progress, setProgress] = useState({ stage: "", pct: 0, message: "" });
  const [detail, setDetail] = useState<GenerationDetail | null>(null);
  const [selected, setSelected] = useState<GeneratorCandidate | null>(null);
  const [error, setError] = useState("");

  const [caption, setCaption] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null);

  const [adObjective, setAdObjective] = useState("OUTCOME_TRAFFIC");
  const [adBudget, setAdBudget] = useState(10000);
  const [adTargetingAgeMin, setAdTargetingAgeMin] = useState(18);
  const [adTargetingAgeMax, setAdTargetingAgeMax] = useState(65);
  const [adTargetingCountries, setAdTargetingCountries] = useState<string[]>(["KR"]);
  const [adStartDate, setAdStartDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [adEndDate, setAdEndDate] = useState<string | null>(null);
  const [advertiseLoading, setAdvertiseLoading] = useState(false);
  const [advertiseResult, setAdvertiseResult] = useState<CampaignResult | null>(null);

  useEffect(() => {
    let id = localStorage.getItem("generator_client_id");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("generator_client_id", id);
    }
    setClientId(id);
    api.generator.brandProfile
      .get(id)
      .then((p) => {
        if (p.brand_color) setBrandColor(p.brand_color);
        if (p.tone_and_manner) setToneAndManner(p.tone_and_manner);
        if (p.brand_logo_key) {
          setLogoS3Key(p.brand_logo_key);
          if (p.brand_logo_url) setLogoPreviewUrl(p.brand_logo_url);
        }
        if (p.brand_color || p.tone_and_manner || p.brand_logo_key) setShowOptional(true);
      })
      .catch(() => {});
  }, []);

  const canStart = productName.trim() && productDescription.trim() && targetAudience.trim();

  function reset() {
    setStep("input");
    setDetail(null);
    setSelected(null);
    setPublishResult(null);
    setCaption("");
    setError("");
  }

  async function handleLogoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !clientId) return;
    if (file.size > 2 * 1024 * 1024) {
      setError("로고 파일은 2MB 이하여야 합니다.");
      return;
    }
    const localUrl = URL.createObjectURL(file);
    setLogoPreviewUrl(localUrl);
    setLogoUploading(true);
    try {
      const result = await api.generator.brandProfile.uploadLogo(clientId, file);
      setLogoS3Key(result.key);
      setLogoPreviewUrl(result.url);
      URL.revokeObjectURL(localUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "로고 업로드에 실패했습니다.");
      setLogoPreviewUrl("");
      setLogoS3Key("");
      URL.revokeObjectURL(localUrl);
    } finally {
      setLogoUploading(false);
    }
  }

  async function saveProfile() {
    if (!clientId) return;
    try {
      await api.generator.brandProfile.save(clientId, {
        brand_color: brandColor || null,
        brand_logo_key: logoS3Key || null,
        tone_and_manner: toneAndManner || null,
      });
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2000);
    } catch {
      setError("브랜드 설정 저장에 실패했습니다.");
    }
  }

  async function startGeneration() {
    setError("");
    setStep("generating");
    setProgress({ stage: "product_analysis", pct: 5, message: "생성 시작..." });
    try {
      const res = (await api.generator.start({
        product_name: productName,
        product_description: productDescription,
        target_audience: targetAudience,
        campaign_objective: objective,
        brand_color: brandColor || null,
        brand_logo_s3_key: logoS3Key || null,
        tone_and_manner: toneAndManner || null,
        width: SIZES[sizeIdx].width,
        height: SIZES[sizeIdx].height,
      })) as { generation_id: string };

      const es = api.generator.stream(res.generation_id);
      es.onmessage = async (e) => {
        const data = JSON.parse(e.data) as SSEProgressEvent;
        if (data.event === "progress") {
          setProgress({ stage: data.stage ?? "", pct: data.pct ?? 0, message: data.message ?? "" });
        } else if (data.event === "completed") {
          es.close();
          try {
            const d = (await api.generator.detail(res.generation_id)) as GenerationDetail;
            setDetail(d);
            setStep("candidates");
          } catch (err) {
            setError(err instanceof Error ? err.message : "생성 결과를 불러오지 못했습니다.");
            setStep("input");
          }
        } else if (data.event === "error") {
          es.close();
          setError(data.message ?? "광고 생성에 실패했습니다.");
          setStep("input");
        }
      };
      es.onerror = () => {
        es.close();
        setError("진행 상태 연결이 끊어졌습니다. 다시 시도해주세요.");
        setStep("input");
      };
    } catch (e) {
      setError(e instanceof Error ? e.message : "광고 생성에 실패했습니다.");
      setStep("input");
    }
  }

  async function selectCandidate(candidate: GeneratorCandidate) {
    if (!detail) return;
    setError("");
    try {
      await api.generator.select(detail.generation_id, candidate.candidate_id);
      setSelected(candidate);
      setPublishResult(null);
      setCaption(`${candidate.copy.headline} — ${candidate.copy.benefit_text}`);
      setStep("selected");
    } catch (e) {
      setError(e instanceof Error ? e.message : "후보 선택에 실패했습니다.");
    }
  }

  async function publish() {
    if (!detail || !selected) return;
    setShowConfirm(false);
    setPublishing(true);
    try {
      const result = (await api.generator.publish(
        detail.generation_id,
        selected.candidate_id,
        caption,
      )) as PublishResult;
      setPublishResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Instagram 게시에 실패했습니다.");
    } finally {
      setPublishing(false);
    }
  }

  async function advertise() {
    if (!detail || !selected) return;
    setError("");
    setAdvertiseLoading(true);
    try {
      const result = (await api.generator.advertise(detail.generation_id, {
        candidate_id: selected.candidate_id,
        budget: adBudget,
        objective: adObjective,
        targeting: {
          age_min: adTargetingAgeMin,
          age_max: adTargetingAgeMax,
          genders: [],
          countries: adTargetingCountries,
        },
        destination_url: "https://example.com",
        start_date: adStartDate,
        end_date: adEndDate,
      })) as CampaignResult;
      setAdvertiseResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Meta 광고 집행에 실패했습니다.");
    } finally {
      setAdvertiseLoading(false);
    }
  }

  const header = (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-2">
        <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 제너레이터</h1>
        {/* 모드 전환 탭 */}
        <div className={`${cardCls} p-1 flex gap-1`}>
          <button
            onClick={() => setPageMode("graph")}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              pageMode === "graph"
                ? "bg-[#3182F6] text-white"
                : "text-[#8B95A1] hover:text-[#333D4B] dark:hover:text-[#E5E8EB]"
            }`}
          >
            전체 생성
          </button>
          <button
            onClick={() => setPageMode("pipeline")}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              pageMode === "pipeline"
                ? "bg-[#3182F6] text-white"
                : "text-[#8B95A1] hover:text-[#333D4B] dark:hover:text-[#E5E8EB]"
            }`}
          >
            빠른 생성
          </button>
        </div>
      </div>
      <p className="text-sm text-[#8B95A1] dark:text-[#6B7280]">
        {pageMode === "graph"
          ? "상품 정보를 입력하면 AI가 전략이 다른 광고 후보 3종을 생성합니다"
          : "AI가 광고 전략을 수립하고 이미지 3종을 직접 생성합니다 · 개선 모드 지원"}
      </p>
    </div>
  );

  /* ─── 빠른 생성 모드 ─── */
  if (pageMode === "pipeline") {
    return (
      <AppLayout>
        <div className="max-w-screen-xl mx-auto px-6 py-8">
          {header}
          <PipelinePage />
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: input ─── */
  if (step === "input") {
    return (
      <AppLayout>
        <div className="max-w-screen-xl mx-auto px-6 py-8">
          {header}

          {error && (
            <div className="mb-6 px-4 py-3 rounded-xl bg-[#FFF0F0] dark:bg-[#3A2228] border border-[#F74D4D]/30 text-sm text-[#F74D4D]">
              {error}
            </div>
          )}

          <div className="grid grid-cols-5 gap-5">
            <div className={`col-span-2 ${cardCls} p-6`}>
              <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">
                생성 설정
              </h2>
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">
                광고 생성 조건을 입력하세요
              </p>

              <div className="space-y-4">
                <div>
                  <label className={labelCls}>
                    제품명 <span className="text-[#F74D4D]">*</span>
                  </label>
                  <input
                    className={inputCls}
                    value={productName}
                    onChange={(e) => setProductName(e.target.value)}
                    placeholder="예: 에어쿨 미니 서큘레이터"
                  />
                </div>

                <div>
                  <label className={labelCls}>
                    제품 설명 <span className="text-[#F74D4D]">*</span>
                  </label>
                  <textarea
                    className={`${inputCls} min-h-24 resize-y`}
                    value={productDescription}
                    onChange={(e) => setProductDescription(e.target.value)}
                    placeholder="제품의 특징, 장점, 차별점을 자유롭게 적어주세요"
                  />
                </div>

                <div>
                  <label className={labelCls}>
                    타겟 <span className="text-[#F74D4D]">*</span>
                  </label>
                  <input
                    className={inputCls}
                    value={targetAudience}
                    onChange={(e) => setTargetAudience(e.target.value)}
                    placeholder="예: 자취하는 20~30대 직장인"
                  />
                </div>

                <div>
                  <label className={labelCls}>
                    광고 목적 <span className="text-[#F74D4D]">*</span>
                  </label>
                  <select
                    className={inputCls}
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                  >
                    {OBJECTIVES.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  type="button"
                  onClick={() => setShowOptional((v) => !v)}
                  className="text-xs font-medium text-[#3182F6] hover:underline"
                >
                  {showOptional ? "▲ 선택 항목 접기" : "▼ 선택 항목 (브랜드 컬러·로고·톤앤매너·사이즈)"}
                </button>

                {showOptional && (
                  <div className="space-y-4 pt-1">
                    <div>
                      <label className={labelCls}>브랜드 컬러</label>
                      <div className="flex gap-2">
                        <input
                          type="color"
                          value={brandColor || "#3182F6"}
                          onChange={(e) => setBrandColor(e.target.value)}
                          className="w-10 h-10 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] cursor-pointer bg-transparent"
                        />
                        <input
                          className={inputCls}
                          value={brandColor}
                          onChange={(e) => setBrandColor(e.target.value)}
                          placeholder="#3182F6"
                        />
                      </div>
                    </div>

                    <div>
                      <label className={labelCls}>브랜드 로고</label>
                      <input
                        ref={logoInputRef}
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/gif"
                        className="hidden"
                        onChange={handleLogoChange}
                      />
                      {logoPreviewUrl ? (
                        <div className="flex items-center gap-3">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={logoPreviewUrl}
                            alt="로고 미리보기"
                            className="w-14 h-14 object-contain rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333]"
                          />
                          <button
                            type="button"
                            disabled={logoUploading}
                            onClick={() => logoInputRef.current?.click()}
                            className="text-xs text-[#3182F6] hover:underline disabled:opacity-50"
                          >
                            {logoUploading ? "업로드 중..." : "다른 파일로 교체"}
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          disabled={logoUploading}
                          onClick={() => logoInputRef.current?.click()}
                          className={`${inputCls} text-left cursor-pointer`}
                        >
                          {logoUploading ? "업로드 중..." : "PNG · JPG · WebP (최대 2MB)"}
                        </button>
                      )}
                    </div>

                    <div>
                      <label className={labelCls}>톤앤매너</label>
                      <input
                        className={inputCls}
                        value={toneAndManner}
                        onChange={(e) => setToneAndManner(e.target.value)}
                        placeholder="예: 산뜻하고 시원한, 신뢰감 있는"
                      />
                    </div>

                    <div>
                      <label className={labelCls}>사이즈</label>
                      <div className="flex gap-2">
                        {SIZES.map((s, i) => (
                          <button
                            key={s.label}
                            type="button"
                            onClick={() => setSizeIdx(i)}
                            className={`px-3 py-2 text-xs rounded-xl border transition-colors ${
                              sizeIdx === i
                                ? "border-[#3182F6] bg-[#3182F6]/10 text-[#3182F6] font-semibold"
                                : "border-[#E5E8EB] dark:border-[#2D3748] text-[#8B95A1] dark:text-[#6B7280]"
                            }`}
                          >
                            {s.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={saveProfile}
                      className="w-full py-2 rounded-xl text-xs font-semibold border border-[#3182F6] text-[#3182F6] hover:bg-[#3182F6]/10 transition-colors"
                    >
                      {profileSaved ? "저장됨 ✓" : "이 브랜드 설정 저장"}
                    </button>
                  </div>
                )}

                <button
                  type="button"
                  disabled={!canStart}
                  onClick={startGeneration}
                  className="w-full py-3 rounded-xl text-sm font-semibold bg-[#3182F6] text-white hover:bg-[#1B64DA] disabled:bg-[#E5E8EB] disabled:text-[#B0B8C1] dark:disabled:bg-[#252D3D] dark:disabled:text-[#4B5563] disabled:cursor-not-allowed transition-colors"
                >
                  광고 후보 3종 생성하기
                </button>
              </div>
            </div>

            <div className={`col-span-3 ${cardCls} p-6`}>
              <h2 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-1">
                생성 결과
              </h2>
              <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-5">
                전략이 서로 다른 광고 후보 3종이 여기에 표시됩니다
              </p>
              <div className="min-h-64 flex items-center justify-center border-2 border-dashed border-[#E5E8EB] dark:border-[#2D3748] rounded-xl">
                <p className="text-xs text-[#B0B8C1] dark:text-[#4B5563]">
                  좌측에서 조건을 입력하고 생성을 시작하세요
                </p>
              </div>
            </div>
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: generating ─── */
  if (step === "generating") {
    const currentIdx = STAGES.findIndex((s) => s.key === progress.stage);
    return (
      <AppLayout>
        <div className="max-w-screen-md mx-auto px-6 py-8">
          {header}
          <div className={`${cardCls} p-8`}>
            <div className="mb-6">
              <div className="flex justify-between items-baseline mb-2">
                <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
                  {progress.message}
                </span>
                <span className="text-xs text-[#8B95A1]">{progress.pct}%</span>
              </div>
              <div className="h-2 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] overflow-hidden">
                <div
                  className="h-full bg-[#3182F6] rounded-full transition-all duration-500"
                  style={{ width: `${progress.pct}%` }}
                />
              </div>
            </div>

            <ul className="space-y-3">
              {STAGES.map((s, i) => {
                const done = currentIdx > i || progress.pct >= 100;
                const active = currentIdx === i;
                return (
                  <li key={s.key} className="flex items-center gap-3 text-sm">
                    <span
                      className={`w-5 h-5 flex items-center justify-center rounded-full text-[10px] font-bold ${
                        done
                          ? "bg-[#00C471] text-white"
                          : active
                            ? "bg-[#3182F6] text-white animate-pulse"
                            : "bg-[#F2F4F6] dark:bg-[#252D3D] text-[#B0B8C1]"
                      }`}
                    >
                      {done ? "✓" : i + 1}
                    </span>
                    <span
                      className={
                        done || active
                          ? "text-[#191F28] dark:text-[#F2F4F6]"
                          : "text-[#B0B8C1] dark:text-[#4B5563]"
                      }
                    >
                      {s.label}
                    </span>
                  </li>
                );
              })}
            </ul>

            <p className="mt-6 text-xs text-[#8B95A1] dark:text-[#6B7280]">
              이미지 3장을 생성하는 데 2~3분 정도 걸릴 수 있어요.
            </p>
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: candidates ─── */
  if (step === "candidates" && detail) {
    return (
      <AppLayout>
        <div className="max-w-screen-xl mx-auto px-6 py-8">
          {header}

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl bg-[#FFF0F0] dark:bg-[#3A2228] border border-[#F74D4D]/30 text-sm text-[#F74D4D]">
              {error}
            </div>
          )}

          <div className="flex items-center justify-between mb-5">
            <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6]">
              광고 후보 3종 — 마음에 드는 광고를 선택하세요
            </h2>
            <button
              type="button"
              onClick={reset}
              className="text-xs text-[#8B95A1] hover:text-[#3182F6] transition-colors"
            >
              새로 생성하기
            </button>
          </div>

          <div className="grid grid-cols-3 gap-5">
            {detail.candidates.map((c) => (
              <button
                key={c.candidate_id}
                type="button"
                onClick={() => selectCandidate(c)}
                className={`${cardCls} p-4 text-left hover:border-[#3182F6] hover:shadow-md cursor-pointer`}
              >
                {c.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={c.image_url}
                    alt={c.copy.headline}
                    className="w-full aspect-square object-cover rounded-xl mb-3 bg-[#F2F4F6] dark:bg-[#252D3D]"
                  />
                ) : (
                  <div className="w-full aspect-square rounded-xl mb-3 bg-[#F2F4F6] dark:bg-[#252D3D]" />
                )}

                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#3182F6]/10 text-[#3182F6]">
                    {c.strategy.name}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1]">
                    Template {c.template_id}
                  </span>
                  <span
                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                      c.qa_passed
                        ? "bg-[#00C471]/10 text-[#00C471]"
                        : "bg-[#F4A100]/10 text-[#F4A100]"
                    }`}
                  >
                    QA {c.qa_passed ? "통과" : "주의"}
                  </span>
                </div>

                <h3 className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">
                  {c.copy.headline}
                </h3>
                <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mt-0.5">
                  {c.copy.subcopy}
                </p>
                <p className="text-xs font-semibold text-[#3182F6] mt-2">CTA: {c.copy.cta}</p>
              </button>
            ))}
          </div>
        </div>
      </AppLayout>
    );
  }

  /* ─── STEP: selected ─── */
  if (step === "selected" && detail && selected) {
    return (
      <AppLayout>
        <div className="max-w-screen-xl mx-auto px-6 py-8">
          {header}
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-base font-semibold text-[#191F28] dark:text-[#F2F4F6]">
              선택한 광고 — {selected.strategy.name}
            </h2>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setStep("candidates")}
                className="text-xs text-[#8B95A1] hover:text-[#3182F6] transition-colors"
              >
                ← 후보 다시 보기
              </button>
              <button
                type="button"
                onClick={reset}
                className="text-xs text-[#8B95A1] hover:text-[#3182F6] transition-colors"
              >
                새로 생성하기
              </button>
            </div>
          </div>

          {error && (
            <div className="mb-5 px-4 py-3 rounded-xl bg-[#FFF0F0] dark:bg-[#3A2228] border border-[#F74D4D]/30 text-sm text-[#F74D4D]">
              {error}
            </div>
          )}

          <div className="grid grid-cols-5 gap-5">
            <div className={`col-span-2 ${cardCls} p-5`}>
              {selected.image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={selected.image_url}
                  alt={selected.copy.headline}
                  className="w-full rounded-xl mb-4 bg-[#F2F4F6] dark:bg-[#252D3D]"
                />
              )}

              <label className={labelCls}>Instagram 캡션</label>
              <textarea
                className={`${inputCls} min-h-20 resize-y mb-3`}
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                placeholder="게시물에 함께 올라갈 캡션을 입력하세요"
              />

              {publishResult ? (
                <div
                  className={`px-4 py-3 rounded-xl text-sm ${
                    publishResult.success
                      ? "bg-[#00C471]/10 text-[#00C471]"
                      : "bg-[#FFF0F0] dark:bg-[#3A2228] text-[#F74D4D]"
                  }`}
                >
                  {publishResult.mocked ? (
                    <>
                      <p className="font-semibold">Mock 모드로 게시 시뮬레이션 완료</p>
                      <p className="text-xs mt-1 opacity-80">
                        META_ACCESS_TOKEN / META_INSTAGRAM_ACCOUNT_ID를 설정하면 실제 Instagram에
                        게시됩니다. (media_id: {publishResult.media_id})
                      </p>
                    </>
                  ) : publishResult.success ? (
                    <p className="font-semibold">
                      Instagram 게시 완료 (media_id: {publishResult.media_id})
                    </p>
                  ) : (
                    <p className="font-semibold">게시 실패: {publishResult.error}</p>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  disabled={publishing}
                  onClick={() => setShowConfirm(true)}
                  className="w-full py-3 rounded-xl text-sm font-semibold bg-[#3182F6] text-white hover:bg-[#1B64DA] disabled:opacity-60 transition-colors"
                >
                  {publishing ? "게시 중..." : "Instagram에 업로드"}
                </button>
              )}

              <section className="mt-6 p-4 border border-[#E5E8EB] dark:border-[#2D3748] rounded-lg">
                <h3 className="mb-2 text-sm font-semibold">Meta 광고 집행</h3>

                {advertiseResult ? (
                  <div
                    className={`px-3 py-2 rounded-md text-sm ${
                      advertiseResult.success
                        ? "bg-[#00C471]/10 text-[#00C471]"
                        : "bg-[#FFF0F0] dark:bg-[#3A2228] text-[#F74D4D]"
                    }`}
                  >
                    {advertiseResult.mocked ? (
                      <>
                        <p className="font-semibold">Mock 모드로 광고 집행 시뮬레이션 완료</p>
                        <p className="text-xs opacity-80">
                          META_AD_ACCOUNT_ID, META_PAGE_ID, META_INSTAGRAM_ACCOUNT_ID,
                          META_ACCESS_TOKEN이 설정되어 있으면 실제 Meta Marketing API로 캠페인이
                          생성됩니다.
                        </p>
                      </>
                    ) : advertiseResult.success ? (
                      <>
                        <p>캠페인 ID: {advertiseResult.campaign_id}</p>
                        <p>광고세트 ID: {advertiseResult.adset_id}</p>
                        <p>크리에이티브 ID: {advertiseResult.creative_id}</p>
                        <p>광고 ID: {advertiseResult.ad_id}</p>
                        <p className="mt-1">
                          <a
                            href={advertiseResult.ads_manager_url || "#"}
                            target="_blank"
                            rel="noreferrer"
                            className="text-[#3182F6] hover:underline"
                          >
                            페이스북 Ads Manager 바로가기
                          </a>
                        </p>
                      </>
                    ) : (
                      <p>광고 집행 실패: {advertiseResult.error}</p>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="mb-3">
                      <label className="block text-xs font-medium mb-1">광고 목적</label>
                      <select
                        className="w-full rounded-md border border-gray-300 px-3 py-1 text-sm"
                        value={adObjective}
                        onChange={(e) => setAdObjective(e.target.value)}
                      >
                        {META_OBJECTIVES.map((obj) => (
                          <option key={obj.value} value={obj.value}>
                            {obj.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="mb-3">
                      <label className="block text-xs font-medium mb-1">일 예산 (원)</label>
                      <input
                        type="number"
                        min={1000}
                        className="w-full rounded-md border border-gray-300 px-3 py-1 text-sm"
                        value={adBudget}
                        onChange={(e) => setAdBudget(Number(e.target.value))}
                        disabled={advertiseLoading}
                      />
                    </div>

                    <div className="mb-3 grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium mb-1">최소 연령</label>
                        <input
                          type="number"
                          min={13}
                          max={adTargetingAgeMax}
                          className="w-full rounded-md border border-gray-300 px-3 py-1 text-sm"
                          value={adTargetingAgeMin}
                          onChange={(e) => setAdTargetingAgeMin(Number(e.target.value))}
                          disabled={advertiseLoading}
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium mb-1">최대 연령</label>
                        <input
                          type="number"
                          min={adTargetingAgeMin}
                          max={100}
                          className="w-full rounded-md border border-gray-300 px-3 py-1 text-sm"
                          value={adTargetingAgeMax}
                          onChange={(e) => setAdTargetingAgeMax(Number(e.target.value))}
                          disabled={advertiseLoading}
                        />
                      </div>
                    </div>

                    <div className="mb-3">
                      <label className="block text-xs font-medium mb-1">
                        국가 코드 (쉼표로 구분)
                      </label>
                      <input
                        type="text"
                        className="w-full rounded-md border border-gray-300 px-3 py-1 text-sm"
                        value={adTargetingCountries.join(",")}
                        onChange={(e) =>
                          setAdTargetingCountries(
                            e.target.value
                              .split(",")
                              .map((c) => c.trim().toUpperCase()),
                          )
                        }
                        disabled={advertiseLoading}
                      />
                    </div>

                    <div className="mb-3">
                      <label className="block text-xs font-medium mb-1">광고 시작일</label>
                      <input
                        type="date"
                        className="w-full rounded-md border border-gray-300 px-3 py-1 text-sm"
                        value={adStartDate}
                        onChange={(e) => setAdStartDate(e.target.value)}
                        disabled={advertiseLoading}
                      />
                    </div>

                    <div className="mb-3">
                      <label className="block text-xs font-medium mb-1">광고 종료일 (선택)</label>
                      <input
                        type="date"
                        className="w-full rounded-md border border-gray-300 px-3 py-1 text-sm"
                        value={adEndDate ?? ""}
                        onChange={(e) => setAdEndDate(e.target.value || null)}
                        disabled={advertiseLoading}
                      />
                    </div>

                    <button
                      type="button"
                      disabled={advertiseLoading || adBudget < 1000}
                      onClick={advertise}
                      className="w-full py-3 rounded-xl text-sm font-semibold bg-[#3182F6] text-white hover:bg-[#1B64DA] disabled:opacity-60 transition-colors"
                    >
                      {advertiseLoading ? "광고 집행 중..." : "Meta 광고 집행"}
                    </button>

                    <p className="mt-2 text-xs text-[#F4A100]">
                      ※ 기본적으로 모든 광고 캠페인, 광고세트, 광고는 PAUSED 상태로 생성됩니다.
                      <br />
                      비용이 발생하지 않으며, 활성화는 Facebook Ads Manager에서 직접 하셔야 합니다.
                    </p>
                  </>
                )}
              </section>
            </div>

            <div className="col-span-3 space-y-5">
              <div className={`${cardCls} p-5`}>
                <h3 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
                  품질 검증 (QA Harness)
                </h3>
                <ul className="grid grid-cols-2 gap-2">
                  {(selected.qa_result?.checks ?? []).map((check) => (
                    <li key={check.name} className="flex items-start gap-2 text-xs">
                      <span
                        className={`mt-0.5 w-4 h-4 shrink-0 flex items-center justify-center rounded-full text-[9px] font-bold ${
                          check.passed ? "bg-[#00C471] text-white" : "bg-[#F4A100] text-white"
                        }`}
                      >
                        {check.passed ? "✓" : "!"}
                      </span>
                      <div>
                        <p className="font-medium text-[#191F28] dark:text-[#F2F4F6]">
                          {QA_LABELS[check.name] ?? check.name}
                        </p>
                        <p className="text-[#8B95A1] dark:text-[#6B7280]">{check.detail}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              {selected.explanation && (
                <div className={`${cardCls} p-5`}>
                  <h3 className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-3">
                    생성 이유
                  </h3>
                  <dl className="space-y-2.5 text-xs">
                    {[
                      ["적용 타겟", selected.explanation.applied_target],
                      ["적용 전략", selected.explanation.applied_strategy],
                      ["적용 템플릿", selected.explanation.applied_template],
                      ["생성 근거", selected.explanation.rationale],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <dt className="font-medium text-[#4E5968] dark:text-[#9CA3AF]">{label}</dt>
                        <dd className="text-[#191F28] dark:text-[#F2F4F6] mt-0.5">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
            </div>
          </div>

          {showConfirm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
              <div className={`${cardCls} w-full max-w-md p-6 mx-4`}>
                <h3 className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">
                  Instagram에 게시할까요?
                </h3>
                <p className="text-xs text-[#8B95A1] dark:text-[#6B7280] mb-4">
                  승인하면 선택한 광고 이미지가 캡션과 함께 Instagram 피드에 게시됩니다. 게시
                  이력은 저장됩니다.
                </p>
                <p className="text-xs text-[#191F28] dark:text-[#F2F4F6] bg-[#F2F4F6] dark:bg-[#252D3D] rounded-xl px-3 py-2 mb-5 line-clamp-3">
                  {caption || "(캡션 없음)"}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowConfirm(false)}
                    className="flex-1 py-2.5 rounded-xl text-sm font-medium border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] transition-colors"
                  >
                    취소
                  </button>
                  <button
                    type="button"
                    onClick={publish}
                    className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-[#3182F6] text-white hover:bg-[#1B64DA] transition-colors"
                  >
                    승인하고 게시
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </AppLayout>
    );
  }

  return null;
}

// ── 공통 인풋 래퍼 (pipeline 전용) ───────────────────────────────────────────

function PipelineField({
  label,
  children,
}: {
  label: string;
  children: React.ReactElement;
}) {
  const inputClass =
    "w-full px-3 py-2 text-sm rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] " +
    "bg-[#F8F9FA] dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] " +
    "placeholder:text-[#B0B8C1] dark:placeholder:text-[#4B5563] " +
    "focus:outline-none focus:border-[#3182F6] focus:ring-1 focus:ring-[#3182F6] transition-colors";

  const child = children as React.ReactElement<{ className?: string }>;
  const styledChild = { ...child, props: { ...child.props, className: inputClass } };

  return (
    <div>
      <label className="block text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1">
        {label}
      </label>
      {styledChild}
    </div>
  );
}
