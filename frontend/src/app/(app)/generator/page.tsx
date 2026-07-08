"use client";

import { useEffect, useRef, useState } from "react";
import { useProjects } from "@/components/ProjectContext";
import { useChatController } from "@/components/chat/ChatController";
import ErrorCard from "@/components/chat/ErrorCard";
import { api, authedFetch, type AutomationRunItem } from "@/lib/api";
import { getJobs, setGenJob } from "@/lib/runningJobs";
import { Select } from "@/components/ui/Select";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
import type {
  BrandKit,
  GenerationDetail,
  GeneratorCandidate,
  PublishResult,
  QualityCheckItem,
  QualityReport,
  RankedAction,
  SSEProgressEvent,
} from "@/lib/types";
import type { ActionResult } from "@/components/manage/types";

// ── 타입 ─────────────────────────────────────────────────────────────────────

type GenMode = "create" | "improve";
type Phase = "idle" | "generating" | "done";

// ── 상수 ─────────────────────────────────────────────────────────────────────

const OBJECTIVES = [
  { value: "awareness", label: "브랜드 인지" },
  { value: "conversion", label: "구매 전환" },
  { value: "lead_gen", label: "리드 수집" },
  { value: "app_install", label: "앱 설치" },
  { value: "retention", label: "재구매 유도" },
  { value: "product_launch", label: "신제품 런칭" },
  { value: "promotion", label: "프로모션 반응" },
];

// Meta 캠페인 목적 — 현재 집행(from-candidate)이 실제 지원하는 건 traffic·leads뿐.
// 나머지는 로드맵 노출용으로 두되 disabled 처리(선택 불가) → 잘못된 값 전송 방지.
const META_OBJECTIVES = [
  { value: "traffic", label: "트래픽 (링크 클릭)", supported: true },
  { value: "leads", label: "리드 (잠재고객 폼)", supported: true },
  { value: "awareness", label: "인지도", supported: false },
  { value: "engagement", label: "참여", supported: false },
  { value: "sales", label: "판매", supported: false },
  { value: "app_promotion", label: "앱 홍보", supported: false },
] as const;

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
  { key: "explain", label: "생성 이유 작성" },
];

const IMPROVE_STAGES = [
  { key: "product_analysis", label: "상품 분석" },
  { key: "strategy", label: "개선 방향 분석" },
  { key: "candidates", label: "광고 생성" },
  { key: "explain", label: "완료" },
];

const CAROUSEL_STAGES = [
  { key: "product_analysis", label: "상품 분석" },
  { key: "strategy", label: "광고 전략 생성" },
  { key: "template", label: "템플릿 선택" },
  { key: "candidates", label: "카드뉴스 3장 생성" },
  { key: "explain", label: "생성 이유 작성" },
];

const STRATEGY_LABELS: Record<string, string> = {
  benefit: "혜택 강조",
  problem_solving: "문제 해결",
  social_proof: "사회적 증거",
  emotional: "감성 접근",
  fomo: "긴급성(FOMO)",
};

const TEMPLATE_LABELS: Record<string, string> = {
  A: "템플릿 A — 제품 강조",
  B: "템플릿 B — 이벤트 강조",
  C: "템플릿 C — 브랜드 강조",
};

const QUALITY_LABELS: Record<keyof Omit<QualityReport, "overall_passed" | "policy_warnings">, string> = {
  typo_check: "오타 검사",
  duplicate_check: "문구 중복",
  cta_exists: "CTA 존재",
  readability: "가독성",
  target_fit: "타겟 적합성",
  text_length: "문구 길이",
  brand_consistency: "브랜드 일관성",
};

const VARIANT_LETTERS = ["A", "B", "C"];

// ── 스타일 ───────────────────────────────────────────────────────────────────

const inputCls =
  "w-full px-3 py-2.5 text-sm rounded-xl border border-line bg-surface-2 text-ink placeholder:text-ink-muted dark:placeholder-[#4B5563] focus:outline-none focus:border-primary transition-colors";
const labelCls = "block text-xs font-medium text-ink-secondary mb-1.5";
const cardCls =
  "bg-card border border-line rounded-2xl transition-colors";

function strategyLabel(t: string): string {
  return STRATEGY_LABELS[t] ?? t;
}

// ── 서브 컴포넌트 ─────────────────────────────────────────────────────────────

function QualityBadge({ item, label }: { item: QualityCheckItem; label: string }) {
  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-line last:border-0">
      <span
        className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold
          ${item.passed ? "bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400" : "bg-red-100 text-red-500 dark:bg-red-900/30 dark:text-red-400"}`}
      >
        {item.passed ? "✓" : "✗"}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-ink-secondary dark:text-[#E5E8EB]">{label}</span>
          <span className="text-[10px] text-ink-tertiary">
            {Math.round(item.score * 100)}점
          </span>
        </div>
        {item.feedback && (
          <p className="text-[11px] text-ink-tertiary mt-0.5">{item.feedback}</p>
        )}
      </div>
    </div>
  );
}

async function downloadImage(imageUrl: string, filename: string) {
  const url = imageUrl.startsWith("/") ? `${API_BASE}${imageUrl}` : imageUrl;
  const res = await fetch(url);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(objectUrl);
}

function CandidateCard({
  candidate,
  onClick,
  isCarousel,
}: {
  candidate: GeneratorCandidate;
  onClick: () => void;
  isCarousel: boolean;
}) {
  const letter = VARIANT_LETTERS[candidate.idx] ?? String(candidate.idx + 1);
  const label = isCarousel ? `슬라이드 ${candidate.idx + 1}` : `${letter}안`;
  const filename = isCarousel
    ? `slide_${candidate.idx + 1}.png`
    : `ad_${letter}.png`;
  return (
    <div
      className="bg-card border border-line rounded-2xl overflow-hidden cursor-pointer group flex hover:border-primary hover:shadow-md transition-all"
      onClick={onClick}
    >
      <div className="relative bg-surface-1 w-52 flex-shrink-0 aspect-square">
        {candidate.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={candidate.image_url?.startsWith("/") ? `${API_BASE}${candidate.image_url}` : candidate.image_url ?? undefined}
            alt={`광고 ${label}`}
            className="w-full h-full object-cover transition-opacity group-hover:opacity-90"
          />
        ) : (
          <div className="w-full h-full" />
        )}
        <div className="absolute top-2 left-2">
          <span className="text-[11px] font-semibold bg-black/50 text-white px-2 py-0.5 rounded-full">
            {label}
          </span>
        </div>
        {candidate.image_url && (
          <button
            type="button"
            className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white rounded-full w-7 h-7 flex items-center justify-center transition-colors"
            title="이미지 다운로드"
            onClick={(e) => {
              e.stopPropagation();
              downloadImage(candidate.image_url!, filename);
            }}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <path d="M8 1a.75.75 0 0 1 .75.75v6.69l1.97-1.97a.75.75 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 7.53a.75.75 0 0 1 1.06-1.06l1.97 1.97V1.75A.75.75 0 0 1 8 1ZM2.5 13.75a.75.75 0 0 1 .75-.75h9.5a.75.75 0 0 1 0 1.5h-9.5a.75.75 0 0 1-.75-.75Z" />
            </svg>
          </button>
        )}
      </div>
      <div className="flex-1 p-5 flex flex-col justify-between min-w-0">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] bg-primary text-primary-foreground px-2 py-0.5 rounded-full">
              {isCarousel
                ? (candidate.strategy.strategy_description ?? `슬라이드 ${candidate.idx + 1}`)
                : strategyLabel(candidate.strategy.strategy_type)}
            </span>
            {!isCarousel && (
              <span className="text-[11px] bg-surface-1 text-ink-tertiary px-2 py-0.5 rounded-full">
                {TEMPLATE_LABELS[candidate.template_id] ?? `템플릿 ${candidate.template_id}`}
              </span>
            )}
            <span
              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                candidate.qa_passed
                  ? "bg-[#00C471]/10 text-[#00C471]"
                  : "bg-[#F4A100]/10 text-[#F4A100]"
              }`}
            >
              QA {candidate.qa_passed ? "통과" : "주의"}
            </span>
          </div>
          <p className="text-sm font-bold text-ink leading-snug line-clamp-2">
            {candidate.copy.headline}
          </p>
          <p className="text-xs text-ink-tertiary leading-relaxed line-clamp-2">
            {candidate.copy.body}
          </p>
        </div>
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-line">
          <span className="text-xs font-semibold text-ink-secondary bg-[#F8F9FA] dark:bg-[#252D3D] px-3 py-1 rounded-lg">
            {candidate.copy.cta}
          </span>
          <span className="text-xs text-primary font-medium">자세히 보기 →</span>
        </div>
      </div>
    </div>
  );
}

// ── 후보 상세 모달 (Instagram 게시 + Meta 광고 집행) ──────────────────────────

function CandidateModal({
  generationId,
  candidate,
  selectError,
  onClose,
  isCarousel,
}: {
  generationId: string;
  candidate: GeneratorCandidate;
  selectError: string | null;
  onClose: () => void;
  isCarousel: boolean;
}) {
  const letter = VARIANT_LETTERS[candidate.idx] ?? String(candidate.idx + 1);
  const label = isCarousel ? `슬라이드 ${candidate.idx + 1}` : `${letter}안`;
  const qa = candidate.qa_result;
  const qualityKeys = Object.keys(QUALITY_LABELS) as (keyof typeof QUALITY_LABELS)[];

  // Instagram 게시
  const [caption, setCaption] = useState(`${candidate.copy.headline}\n\n${candidate.copy.body}`);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);

  // Meta 광고 집행 — 시뮬 없는 빠른 집행(from-candidate→approve→execute, PAUSED 생성)
  const [campaignName, setCampaignName] = useState(candidate.copy.headline);
  const [adObjective, setAdObjective] = useState<"traffic" | "leads">("traffic");
  const [linkUrl, setLinkUrl] = useState("");
  const [adBudget, setAdBudget] = useState(10000);
  const [startDate, setStartDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [endDate, setEndDate] = useState<string | null>(null);
  const [ageMin, setAgeMin] = useState(18);
  const [ageMax, setAgeMax] = useState(65);
  const [countries, setCountries] = useState<string[]>(["KR"]);
  const [advertising, setAdvertising] = useState(false);
  const [advertiseResult, setAdvertiseResult] = useState<ActionResult | null>(null);
  const [advertiseError, setAdvertiseError] = useState<string | null>(null);

  async function handlePublish() {
    setPublishing(true);
    setPublishError(null);
    try {
      const result = (await api.generator.publish(
        generationId,
        candidate.candidate_id,
        caption,
      )) as PublishResult;
      setPublishResult(result);
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : "Instagram 게시에 실패했습니다.");
    } finally {
      setPublishing(false);
    }
  }

  async function handleAdvertise() {
    if (!linkUrl.trim()) {
      setAdvertiseError("목적지 URL(link_url)을 입력하세요.");
      return;
    }
    setAdvertising(true);
    setAdvertiseError(null);
    setAdvertiseResult(null);
    try {
      // 집행은 management 단일 경로로 일원화 — 후보를 제안으로 패키징한 뒤 승인·실행.
      const { proposal } = await api.management.fromCandidate({
        generation_id: generationId,
        candidate_id: candidate.candidate_id,
        objective: adObjective,
        link_url: linkUrl.trim(),
        name: campaignName.trim() || candidate.copy.headline,
        daily_budget_krw: adBudget,
        start_date: startDate,
        end_date: endDate,
        country: countries[0] ?? "KR",
        age_min: ageMin,
        age_max: ageMax,
        gender: "all",
      });
      const a = (await api.management.approve(proposal, true)) as { approved_action: unknown };
      const resp = (await api.management.execute(a.approved_action, proposal)) as {
        result: ActionResult;
        error_message?: string;
      };
      setAdvertiseResult(resp.result);
      if (resp.error_message) setAdvertiseError(resp.error_message);
    } catch (e) {
      setAdvertiseError(e instanceof Error ? e.message : "Meta 광고 집행에 실패했습니다.");
    } finally {
      setAdvertising(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative bg-card rounded-2xl w-full max-w-5xl max-h-[92vh] flex overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 w-8 h-8 rounded-full bg-black/40 hover:bg-black/60 flex items-center justify-center transition-colors"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div className="w-[45%] flex-shrink-0 bg-[#0D1117] flex items-center justify-center">
          {candidate.image_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={candidate.image_url?.startsWith("/") ? `${API_BASE}${candidate.image_url}` : candidate.image_url ?? undefined}
              alt={`광고 ${label}`}
              className="w-full h-full object-contain"
            />
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="sticky top-0 bg-card border-b border-line px-6 py-4 flex items-center gap-2">
            <span className="text-sm font-bold text-ink">{label}</span>
            <span className="text-[11px] bg-primary text-primary-foreground px-2 py-0.5 rounded-full">
              {isCarousel
                ? (candidate.strategy.strategy_description ?? `슬라이드 ${candidate.idx + 1}`)
                : strategyLabel(candidate.strategy.strategy_type)}
            </span>
            {!isCarousel && (
              <span className="text-[11px] bg-surface-1 text-ink-secondary px-2 py-0.5 rounded-full">
                {TEMPLATE_LABELS[candidate.template_id] ?? `템플릿 ${candidate.template_id}`}
              </span>
            )}
          </div>

          <div className="p-6 space-y-6">
            {selectError && (
              <p className="text-xs text-[#F4A100] bg-[#F4A100]/10 rounded-lg px-3 py-2">
                후보 선택 동기화 경고: {selectError} (게시·집행이 실패할 수 있습니다)
              </p>
            )}

            {/* 광고 카피 */}
            <section className="space-y-4">
              <h3 className="text-xs font-bold text-ink-tertiary uppercase tracking-widest">
                광고 카피
              </h3>
              <div className="bg-[#F8F9FA] dark:bg-[#252D3D] rounded-xl p-4 space-y-3">
                <div>
                  <p className="text-[10px] font-semibold text-ink-tertiary mb-1 uppercase tracking-wide">
                    헤드라인
                  </p>
                  <p className="text-base font-bold text-ink leading-snug">
                    {candidate.copy.headline}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold text-ink-tertiary mb-1 uppercase tracking-wide">
                    본문
                  </p>
                  <p className="text-sm text-ink-secondary leading-relaxed">
                    {candidate.copy.body}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold text-ink-tertiary mb-1 uppercase tracking-wide">
                    CTA
                  </p>
                  <span className="inline-block text-sm font-semibold bg-primary text-primary-foreground px-4 py-1.5 rounded-lg">
                    {candidate.copy.cta}
                  </span>
                </div>
              </div>
            </section>

            {/* 생성 이유 */}
            {candidate.explanation && (
              <section className="space-y-2">
                <h3 className="text-xs font-bold text-ink-tertiary uppercase tracking-widest">
                  생성 이유
                </h3>
                <dl className="space-y-2 text-sm">
                  {[
                    ["적용 타겟", candidate.explanation.applied_target],
                    ["적용 전략", candidate.explanation.applied_strategy],
                    ["적용 템플릿", candidate.explanation.applied_template],
                    ["생성 근거", candidate.explanation.rationale],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-[11px] font-medium text-ink-tertiary">
                        {label}
                      </dt>
                      <dd className="text-ink-secondary mt-0.5 leading-relaxed">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}

            {/* 품질 검증 */}
            {qa && (
              <section className="space-y-3">
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold text-ink-tertiary uppercase tracking-widest">
                    품질 검증
                  </h3>
                  <span
                    className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                      qa.overall_passed
                        ? "bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400"
                        : "bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400"
                    }`}
                  >
                    {qa.overall_passed ? "전체 통과" : "일부 주의"}
                  </span>
                </div>
                <div className="bg-[#F8F9FA] dark:bg-[#252D3D] rounded-xl p-3">
                  {qualityKeys.map((key) => (
                    <QualityBadge key={key} item={qa[key]} label={QUALITY_LABELS[key]} />
                  ))}
                </div>
              </section>
            )}

            {/* 저장 경로 */}
            <section className="space-y-1">
              <h3 className="text-xs font-bold text-ink-tertiary uppercase tracking-widest">
                저장 경로
              </h3>
              <p className="text-xs text-ink-muted font-mono break-all">
                {candidate.s3_key}
              </p>
            </section>

            {/* Instagram 게시 */}
            <section className="space-y-3 pt-2 border-t border-line">
              <h3 className="text-xs font-bold text-ink-tertiary uppercase tracking-widest">
                Instagram 게시
              </h3>
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
                        META_ACCESS_TOKEN / META_INSTAGRAM_ACCOUNT_ID를 설정하면 실제로 게시됩니다.
                        (media_id: {publishResult.media_id})
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
                <>
                  <div>
                    <label className="block text-xs font-medium text-ink-secondary mb-1">
                      캡션 ({caption.length} / 2,200)
                    </label>
                    <textarea
                      value={caption}
                      onChange={(e) => setCaption(e.target.value)}
                      maxLength={2200}
                      rows={4}
                      placeholder="인스타그램 캡션을 입력하세요 (해시태그 포함)"
                      className="w-full px-3 py-2 text-sm rounded-xl border border-line bg-[#F8F9FA] dark:bg-[#252D3D] text-ink placeholder:text-ink-muted dark:placeholder:text-ink-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors resize-none"
                    />
                  </div>
                  {publishError && (
                    <p className="text-xs text-red-600 dark:text-red-400">{publishError}</p>
                  )}
                  <button
                    onClick={handlePublish}
                    disabled={publishing || !caption.trim()}
                    className="w-full py-2.5 rounded-xl text-sm font-semibold text-white bg-primary hover:bg-primary-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {publishing ? "게시 중..." : "Instagram에 게시"}
                  </button>
                </>
              )}
            </section>

            {/* Meta 광고 집행 */}
            <section className="space-y-3 pt-2 border-t border-line">
              <h3 className="text-xs font-bold text-ink-tertiary uppercase tracking-widest">
                캠페인 생성
              </h3>
              {advertiseResult ? (
                <div
                  className={`px-3 py-3 rounded-xl text-sm ${
                    advertiseResult.status === "success"
                      ? "bg-[#00C471]/10 text-[#00C471]"
                      : "bg-[#FFF0F0] dark:bg-[#3A2228] text-[#F74D4D]"
                  }`}
                >
                  {advertiseResult.status === "success" ? (
                    advertiseResult.platform_response_snapshot?.campaign_meta_id ? (
                      <div className="space-y-0.5">
                        <p className="font-semibold">캠페인 생성 완료 (PAUSED)</p>
                        <p>
                          캠페인 ID: {advertiseResult.platform_response_snapshot.campaign_meta_id}
                        </p>
                        <p className="text-xs opacity-80 mt-1">
                          캠페인·광고세트가 PAUSED로 생성됐습니다(미게재·과금 0). 광고 소재(리드
                          캠페인은 리드폼 포함)는 Meta Ads Manager에서 추가한 뒤 거기서 게재하세요.
                        </p>
                      </div>
                    ) : (
                      <>
                        <p className="font-semibold">캠페인 생성 절차 검증 완료</p>
                        <p className="text-xs opacity-80 mt-1">
                          현재 모드에선 실제 생성이 일어나지 않습니다(검증/모의). LIVE 모드일 때 실제
                          Meta 캠페인이 PAUSED로 생성됩니다.
                        </p>
                      </>
                    )
                  ) : (
                    <p>광고 집행 실패: {advertiseError ?? "알 수 없는 오류"}</p>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-ink-secondary mb-1">
                      캠페인 이름
                    </label>
                    <input
                      type="text"
                      className={inputCls}
                      value={campaignName}
                      onChange={(e) => setCampaignName(e.target.value)}
                      disabled={advertising}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-ink-secondary mb-1">
                      광고 목적
                    </label>
                    <Select
                      aria-label="광고 목적"
                      value={adObjective}
                      onChange={(v) => setAdObjective(v as "traffic" | "leads")}
                      disabled={advertising}
                      options={META_OBJECTIVES.map((o) => ({
                        value: o.value,
                        label: o.supported ? o.label : `${o.label} (준비 중)`,
                        disabled: !o.supported,
                      }))}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-ink-secondary mb-1">
                      목적지 URL
                    </label>
                    <input
                      type="url"
                      placeholder="https://example.com/landing"
                      className={inputCls}
                      value={linkUrl}
                      onChange={(e) => setLinkUrl(e.target.value)}
                      disabled={advertising}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-ink-secondary mb-1">
                      일 예산 (원)
                    </label>
                    <input
                      type="number"
                      min={1000}
                      className={inputCls}
                      value={adBudget}
                      onChange={(e) => setAdBudget(Number(e.target.value))}
                      disabled={advertising}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-ink-secondary mb-1">
                        최소 연령
                      </label>
                      <input
                        type="number"
                        min={13}
                        max={ageMax}
                        className={inputCls}
                        value={ageMin}
                        onChange={(e) => setAgeMin(Number(e.target.value))}
                        disabled={advertising}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-ink-secondary mb-1">
                        최대 연령
                      </label>
                      <input
                        type="number"
                        min={ageMin}
                        max={100}
                        className={inputCls}
                        value={ageMax}
                        onChange={(e) => setAgeMax(Number(e.target.value))}
                        disabled={advertising}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-ink-secondary mb-1">
                      국가 코드 (쉼표로 구분)
                    </label>
                    <input
                      type="text"
                      className={inputCls}
                      value={countries.join(",")}
                      onChange={(e) =>
                        setCountries(e.target.value.split(",").map((c) => c.trim().toUpperCase()))
                      }
                      disabled={advertising}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-ink-secondary mb-1">
                        광고 시작일
                      </label>
                      <input
                        type="date"
                        className={inputCls}
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                        disabled={advertising}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-ink-secondary mb-1">
                        광고 종료일 (선택)
                      </label>
                      <input
                        type="date"
                        className={inputCls}
                        value={endDate ?? ""}
                        onChange={(e) => setEndDate(e.target.value || null)}
                        disabled={advertising}
                      />
                    </div>
                  </div>
                  {advertiseError && (
                    <p className="text-xs text-red-600 dark:text-red-400">{advertiseError}</p>
                  )}
                  <p className="text-[11px] text-ink-tertiary">
                    예산·타겟까지 Meta에 캠페인을 만듭니다. 게재는 안 되며(PAUSED), 광고 소재는 Meta
                    Ads Manager에서 추가하세요.
                  </p>
                  <button
                    onClick={handleAdvertise}
                    disabled={advertising || adBudget < 1000}
                    className="w-full py-2.5 rounded-xl text-sm font-semibold text-white bg-primary hover:bg-primary-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {advertising ? "생성 중..." : "캠페인 생성하기"}
                  </button>
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

// 진행 중인 생성 ID — 페이지 이탈/새로고침 후 복원용
const ACTIVE_GEN_KEY = "generator_active_gen";

// 광고 asset_url(전체 URL / 프록시 경로 / S3 키 / 로컬 파일경로) → 미리보기 가능한 src.
// 로컬 파일경로(C:\..., 백슬래시 포함) 등 표시 불가하면 null.
function adRefImageSrc(asset: string): string | null {
  if (/^https?:\/\//.test(asset)) return asset;
  if (asset.startsWith("/")) return `${API_BASE}${asset}`;
  if (/[\\]/.test(asset) || /^[A-Za-z]:/.test(asset)) return null;
  return `${API_BASE}/api/generator/image?key=${encodeURIComponent(asset)}`;
}

// 서버 워커(APScheduler)가 자동으로 남긴 생성 도메인 점검 결과 — 결과 없으면 렌더하지 않음
// (워커 꺼진 dev/발표 환경에서 빈 카드 노이즈 방지). manage/anomaly의 workerRuns 카드와 동일 패턴.
function WorkerRunsCard({ runs }: { runs: AutomationRunItem[] }) {
  if (runs.length === 0) return null;
  return (
    <div className={`${cardCls} p-6`}>
      <p className="text-sm font-semibold text-ink">서버 자동 점검 결과</p>
      <p className="text-[12px] text-ink-tertiary mt-0.5">
        백엔드 워커가 주기적으로 스스로 점검해 남긴 생성 품질·상태 결과예요. 이 화면을 열어두지
        않아도 서버가 자동으로 쌓아둡니다.
      </p>
      <ul className="mt-2 space-y-1.5">
        {runs.map((r) => (
          <li key={r.id} className="rounded-lg bg-surface-1 px-3 py-2">
            <p className="text-[12px] font-semibold text-ink">
              {r.title || r.job_name}
              {r.created_at && (
                <span className="ml-2 font-normal text-ink-muted">
                  {r.created_at.slice(0, 16).replace("T", " ")}
                </span>
              )}
            </p>
            {r.body && <p className="text-[12px] text-ink-tertiary">{r.body}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function GeneratorPage() {
  const { projects, details, loadDetails, refreshDetails } = useProjects();
  // 화면 내 프로젝트 선택은 로컬 상태 — 사이드바(전역 선택)와 동기화하지 않는다.
  // 진입 시 전역 선택(localStorage)을 초기값으로만 읽고, 이후 변경은 이 화면에만 반영된다.
  const [localProjectId, setLocalProjectId] = useState<string | null>(null);
  useEffect(() => {
    setLocalProjectId(localStorage.getItem("selectedProjectId"));
  }, []);
  const selectedProject = projects.find((p) => p.id === localProjectId) ?? null;
  const selectProject = (id: string | null) => setLocalProjectId(id);
  // N2 — 안읽음 뱃지(시뮬 경로와 대칭). 닫힘 여부는 ref로 최신값 읽음.
  const { pushUnread, floatingOpen, openChat } = useChatController();
  const floatingOpenRef = useRef(floatingOpen);
  useEffect(() => {
    floatingOpenRef.current = floatingOpen;
  }, [floatingOpen]);
  const [mode, setMode] = useState<GenMode>("create");
  const [format, setFormat] = useState<"single" | "carousel">("single");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");

  // 브랜드 캐시 / 로고
  const [clientId, setClientId] = useState("");
  const [logoS3Key, setLogoS3Key] = useState("");
  const [logoPreviewUrl, setLogoPreviewUrl] = useState("");
  const [logoUploading, setLogoUploading] = useState(false);

  // 브랜드 키트 (조직 단위 저장/불러오기)
  const [kits, setKits] = useState<BrandKit[]>([]);
  const [selectedKitId, setSelectedKitId] = useState("");
  const [kitName, setKitName] = useState("");
  const logoInputRef = useRef<HTMLInputElement>(null);
  const colorInputRef = useRef<HTMLInputElement>(null);
  const esRef = useRef<EventSource | null>(null);

  // 상품 이미지 (생성 모드)
  const [productImageTempKey, setProductImageTempKey] = useState("");
  const [productImagePreviewUrl, setProductImagePreviewUrl] = useState("");
  const [productImageUploading, setProductImageUploading] = useState(false);
  const productImageInputRef = useRef<HTMLInputElement>(null);

  // 공통 옵션
  const [showOptional, setShowOptional] = useState(false);
  const [brandColor, setBrandColor] = useState("");
  const [toneAndManner, setToneAndManner] = useState("");
  const [sizeIdx, setSizeIdx] = useState(0);

  // 생성 모드 입력
  const [productName, setProductName] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [objective, setObjective] = useState("conversion");

  // 개선 모드 입력 — 시뮬레이션 선택 → 자동 로드
  const [selectedSimId, setSelectedSimId] = useState("");
  const [improveData, setImproveData] = useState<{
    ad_asset_url: string | null;
    product_name: string;
    summary: string;
    improvement_direction: string;
    plain_summary: string | null;
    product_cutout_s3_key: string | null;
  } | null>(null);
  const [improveLoading, setImproveLoading] = useState(false);
  const [improveError, setImproveError] = useState("");
  // CREATE 모드 생성 완료 시 누끼 S3 키 보관 (개선 모드에서 재사용)
  const lastProductCutoutKeyRef = useRef<string | null>(null);
  const [fixRequests, setFixRequests] = useState("");

  // 진행 / 결과
  const [progress, setProgress] = useState({ stage: "", pct: 0, message: "" });
  const [detail, setDetail] = useState<GenerationDetail | null>(null);
  const [modalCandidate, setModalCandidate] = useState<GeneratorCandidate | null>(null);
  const [selectError, setSelectError] = useState<string | null>(null);

  // 서버 워커(APScheduler)가 남긴 생성 도메인 자동 점검 결과 — 진입 시 1회 읽기만.
  const [workerRuns, setWorkerRuns] = useState<AutomationRunItem[]>([]);
  useEffect(() => {
    api.automation
      .runs({ domain: "generation", limit: 5 })
      .then((r) => setWorkerRuns(r.runs))
      .catch(() => setWorkerRuns([]));
  }, []);

  useEffect(() => {
    let id = localStorage.getItem("generator_client_id");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("generator_client_id", id);
    }
    setClientId(id);
    // 첫 진입 시 브랜드 필드(컬러·톤·로고)는 비워둔다.
    // 저장된 브랜드 키트를 선택할 때만 applyKit으로 값이 적용된다.
  }, []);

  // 진행 중이던 생성 복원 — 마운트 시 저장된 generation_id가 있으면 상태 확인 후 재연결
  useEffect(() => {
    const activeId = localStorage.getItem(ACTIVE_GEN_KEY);
    if (!activeId) return;
    let cancelled = false;
    (async () => {
      try {
        const d = (await api.generator.detail(activeId)) as GenerationDetail;
        if (cancelled) return;
        if (d.status === "completed") {
          setDetail(d);
          setPhase("done");
          localStorage.removeItem(ACTIVE_GEN_KEY);
        } else if (d.status === "failed") {
          setError(d.error_message || "광고 생성에 실패했습니다.");
          setPhase("idle");
          localStorage.removeItem(ACTIVE_GEN_KEY);
        } else {
          // pending/running — 진행 중. SSE 재연결(서버 재시작으로 스트림 유실 시 onmessage error로 정리)
          setPhase("generating");
          setProgress({ stage: "", pct: 5, message: "진행 상태를 다시 불러오는 중..." });
          subscribe(activeId);
        }
      } catch {
        // 조회 실패(404 등) → 오래된 ID 정리
        localStorage.removeItem(ACTIVE_GEN_KEY);
      }
    })();
    return () => {
      cancelled = true;
      esRef.current?.close();
    };
  }, []);

  // 개선 모드: 프로젝트 선택 시 해당 프로젝트 시뮬 목록 로드 + 시뮬 선택 초기화
  useEffect(() => {
    setSelectedSimId("");
    setImproveData(null);
    setImproveError("");
    if (mode === "improve" && selectedProject) {
      loadDetails(selectedProject.id);
    }
  }, [mode, selectedProject?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const improveSims = (selectedProject && details[selectedProject.id]?.sims) || [];

  function buildSimSummary(agg: Record<string, number | null>, n?: number): string {
    const parts: string[] = [];
    if (n) parts.push(`표본 ${n}명`);
    if (agg.purchase_intent != null) parts.push(`구매의향 ${agg.purchase_intent.toFixed(2)}/5`);
    if (agg.click_intent_rate != null) parts.push(`클릭의향 ${Math.round(agg.click_intent_rate * 100)}%`);
    if (agg.trust_avg != null) parts.push(`신뢰도 ${agg.trust_avg.toFixed(2)}/5`);
    if (agg.rejection_rate != null) parts.push(`거부율 ${Math.round(agg.rejection_rate * 100)}%`);
    return parts.join(" · ");
  }

  // 시뮬 선택 → 제품명·결과요약·개선방향(토론 권고)·광고 이미지 자동 로드
  async function loadSimulation(simId: string) {
    setSelectedSimId(simId);
    setImproveData(null);
    setImproveError("");
    if (!simId) return;
    setImproveLoading(true);
    try {
      const r = await authedFetch(`${API_BASE}/api/projects/simulations/${simId}`);
      if (!r.ok) throw new Error(`시뮬레이션 조회 실패 (HTTP ${r.status})`);
      const detail = await r.json();
      const agg = (detail.aggregate ?? {}) as Record<string, number | null>;
      const productName: string = detail.ad_title ?? "";
      const summary =
        buildSimSummary(agg, detail.sample_size) || `${productName || "광고"} 시뮬레이션 결과`;

      // 개선방향·AI 분석(토론 리포트) — 토론 없거나 실패해도 무시(개선방향만 비움)
      let direction = "";
      let plainSummary: string | null = null;
      try {
        const rep = await authedFetch(`${API_BASE}/api/debate/by-simulation/${simId}/report`);
        if (rep.ok) {
          const rv = (await rep.json()) as {
            report?: { ranked_actions?: RankedAction[]; plain_summary?: string };
          };
          plainSummary = rv.report?.plain_summary ?? null;
          const actions = rv.report?.ranked_actions ?? [];
          if (actions.length) {
            direction = actions
              .map(
                (a, i) =>
                  `${i + 1}. ${a.action}${a.expected_effect ? ` — ${a.expected_effect}` : ""}`,
              )
              .join("\n");
          }
        }
      } catch {
        /* 토론 리포트 없음/실패 — 개선방향 비움 */
      }
      setImproveData({
        ad_asset_url: detail.ad_asset_url ?? null,
        product_name: productName,
        summary,
        improvement_direction: direction,
        plain_summary: plainSummary,
        product_cutout_s3_key: lastProductCutoutKeyRef.current,
      });
    } catch {
      setImproveError("시뮬레이션 정보를 불러오지 못했습니다.");
    } finally {
      setImproveLoading(false);
    }
  }

  const canSubmit =
    mode === "create"
      ? productName.trim() && productDescription.trim() && targetAudience.trim()
      : !!improveData?.summary;

  // SSE 구독 — 시작/복원 공용. 완료·실패 시 localStorage 정리.
  function subscribe(generationId: string) {
    esRef.current?.close();
    setGenJob(generationId); // 동시실행 슬롯 점유(제너 1개 제한, 채팅 위젯과 store 공유)
    const es = api.generator.stream(generationId);
    esRef.current = es;
    es.onmessage = async (e) => {
      const data = JSON.parse(e.data) as SSEProgressEvent;
      if (data.event === "progress") {
        setProgress({ stage: data.stage ?? "", pct: data.pct ?? 0, message: data.message ?? "" });
      } else if (data.event === "completed") {
        es.close();
        localStorage.removeItem(ACTIVE_GEN_KEY);
        setGenJob(null); // 동시실행 슬롯 해제
        try {
          const d = (await api.generator.detail(generationId)) as GenerationDetail;
          // CREATE 완료 시 누끼 S3 키 보관 — 개선 모드에서 재사용
          if (d.product_cutout_s3_key) {
            lastProductCutoutKeyRef.current = d.product_cutout_s3_key;
          }
          setDetail(d);
          setPhase("done");
          // 완료된 생성물을 좌측 패널 목록에 즉시 반영(새로고침 불필요).
          if (selectedProject?.id) refreshDetails(selectedProject.id);
          // N1 — 전용 페이지 직접 생성이 끝나면, 개선/시뮬 제안을 채팅에 자동 주입.
          // 기존 대화에 끼워넣지 않고 '새 채팅 세션'을 만들어 거기에 제안한다(맥락 분리).
          // 만든 세션 id는 저장해 아래 '시뮬레이션 돌리기' 버튼(#2)이 같은 세션을 연다.
          const pid = selectedProject?.id;
          if (pid) {
            const injectKey = `n1_gen_injected_${generationId}`; // 동일 생성 1회만
            if (!localStorage.getItem(injectKey)) {
              localStorage.setItem(injectKey, "1");
              const count = (d.candidates ?? []).length;
              // 첫 후보를 시뮬 제안 프리필로 — 시안 카피 + 이미지 URL(시뮬 이미지 필수 충족).
              const c0 = (d.candidates ?? [])[0];
              const simImgRaw = c0?.image_url ?? null;
              const simImg = simImgRaw
                ? simImgRaw.startsWith("/")
                  ? `${API_BASE}${simImgRaw}`
                  : simImgRaw
                : undefined;
              const sessionTitle = `${productName || "광고 시안"} 시뮬·개선`;
              api.chat.createSession(pid, sessionTitle).then((created) => {
                const sid = created.id;
                // #2 버튼이 이 제안 세션을 열 수 있게 생성별로 저장.
                localStorage.setItem(`gen_sim_session_${generationId}`, sid);
                void api.chat
                  .appendWidgets(sid, [
                    {
                      content: `광고 시안 ${count}개가 생성됐어요. 채팅에서 이어서 개선해볼까요?`,
                      meta: {
                        source: "generator",
                        label: "광고 생성",
                        approval: {
                          action: "run_generator",
                          label: "개선 시안 다시 생성",
                          reasons: ["전용 페이지에서 직접 만든 시안을 채팅에서 이어 개선할 수 있어요."],
                        },
                      },
                    },
                    // #3 — 생성 완료 시 시뮬레이션 제안(첫 시안 프리필). 이미지 URL로 시뮬 즉시 실행 가능.
                    ...(c0
                      ? [
                          {
                            content:
                              "생성한 시안으로 소비자 반응을 미리 예측해볼까요? 아래에서 확인·실행하세요.",
                            meta: {
                              source: "simulation",
                              label: "시뮬레이션",
                              widget: {
                                type: "sim_form",
                                data: {
                                  ad_title: c0.copy.headline,
                                  ad_content: [c0.copy.headline, c0.copy.body, c0.copy.cta]
                                    .filter(Boolean)
                                    .join("\n"),
                                  ad_image_url: simImg,
                                },
                              },
                            },
                          },
                        ]
                      : []),
                  ])
                  .then(() => {
                    if (!floatingOpenRef.current) pushUnread();
                  })
                  .catch(() => {});
              }).catch(() => {});
            }
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : "생성 결과를 불러오지 못했습니다.");
          setPhase("idle");
        }
      } else if (data.event === "error") {
        es.close();
        localStorage.removeItem(ACTIVE_GEN_KEY);
        setGenJob(null); // 동시실행 슬롯 해제
        setError(data.message ?? "광고 생성에 실패했습니다.");
        setPhase("idle");
      }
    };
    es.onerror = async () => {
      es.close();
      localStorage.removeItem(ACTIVE_GEN_KEY);
      setGenJob(null); // 동시실행 슬롯 해제
      // 스트림이 끊긴 이유가 서버측 생성 실패(error 이벤트가 종료 전 유실)일 수 있다.
      // 상태를 조회해 실제 실패 원인이 있으면 그걸 우선 노출 — "네트워크 끊김"으로 오인 방지.
      try {
        const d = (await api.generator.detail(generationId)) as GenerationDetail;
        if (d.status === "failed") {
          setError(d.error_message || "광고 생성에 실패했습니다.");
          setPhase("idle");
          return;
        }
      } catch {
        // 조회 실패 시 아래 일반 안내로 폴백
      }
      setError("진행 상태 연결이 끊어졌습니다. 다시 시도해주세요.");
      setPhase("idle");
    };
  }

  function resetResult() {
    setPhase("idle");
    setDetail(null);
    setError("");
  }

  // ── 브랜드 키트 ─────────────────────────────────────────────────────────────
  async function loadKits() {
    try {
      const { kits } = await api.generator.brandKits.list();
      setKits(kits);
    } catch {
      /* 미로그인·네트워크 오류 시 빈 목록 유지 */
    }
  }

  useEffect(() => {
    loadKits();
  }, []);

  function applyKit(id: string) {
    setSelectedKitId(id);
    const kit = kits.find((k) => k.id === id);
    if (!kit) return;
    setBrandColor(kit.brand_color ?? "");
    setLogoS3Key(kit.brand_logo_key ?? "");
    setLogoPreviewUrl(
      kit.brand_logo_key
        ? `${API_BASE}/api/generator/image?key=${encodeURIComponent(kit.brand_logo_key)}`
        : "",
    );
    setToneAndManner(kit.tone_and_manner ?? "");
  }

  async function saveKit() {
    if (!kitName.trim()) return;
    try {
      await api.generator.brandKits.create({
        name: kitName.trim(),
        brand_color: brandColor || null,
        brand_logo_key: logoS3Key || null,
        tone_and_manner: toneAndManner || null,
      });
      setKitName("");
      await loadKits();
    } catch (e) {
      setError(e instanceof Error ? e.message : "브랜드 키트 저장에 실패했습니다.");
    }
  }

  async function deleteKit() {
    if (!selectedKitId) return;
    try {
      await api.generator.brandKits.remove(selectedKitId);
      setSelectedKitId("");
      await loadKits();
    } catch {
      /* 무시 */
    }
  }

  async function handleProductImageChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) {
      setError("상품 이미지는 4MB 이하여야 합니다.");
      return;
    }
    const localUrl = URL.createObjectURL(file);
    setProductImagePreviewUrl(localUrl);
    setProductImageUploading(true);
    try {
      const result = await api.generator.uploadProductImage(file);
      setProductImageTempKey(result.temp_key);
    } catch (err) {
      setError(err instanceof Error ? err.message : "상품 이미지 업로드에 실패했습니다.");
      setProductImagePreviewUrl("");
      setProductImageTempKey("");
      URL.revokeObjectURL(localUrl);
    } finally {
      setProductImageUploading(false);
    }
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

  async function startGeneration() {
    if (phase === "generating") return; // 재생성 연타 방지
    setError("");
    // 동시실행 제한 — 제너는 한 번에 하나(채팅 위젯과 store 공유).
    if (getJobs().gen) {
      setError("이미 다른 광고 생성이 진행 중이에요. 끝난 뒤 다시 시도하세요.");
      return;
    }
    // 생성 내역이 프로젝트에 기록되도록 활성 프로젝트를 강제 — 미선택 시 차단(내역 누락 방지).
    if (!selectedProject) {
      setError("생성 내역을 저장할 프로젝트를 먼저 선택하세요.");
      return;
    }
    setDetail(null);
    setPhase("generating");
    setProgress({ stage: "product_analysis", pct: 5, message: "생성 시작..." });

    const common = {
      project_id: selectedProject?.id ?? null,
      brand_color: brandColor || null,
      brand_logo_s3_key: logoS3Key || null,
      tone_and_manner: toneAndManner || null,
      width: SIZES[sizeIdx].width,
      height: SIZES[sizeIdx].height,
    };
    const body =
      mode === "create"
        ? {
            ...common,
            mode: "create",
            format,
            product_name: productName,
            product_description: productDescription,
            target_audience: targetAudience,
            campaign_objective: objective,
            product_image_temp_key: productImageTempKey || null,
          }
        : {
            ...common,
            mode: "improve",
            product_name: improveData?.product_name || "",
            simulation_summary: improveData?.summary || "",
            plain_summary: improveData?.plain_summary || null,
            improvement_direction: improveData?.improvement_direction || null,
            fix_requests: fixRequests || null,
            product_cutout_s3_key: improveData?.product_cutout_s3_key || null,
          };

    try {
      const res = (await api.generator.start(body)) as { generation_id: string };
      localStorage.setItem(ACTIVE_GEN_KEY, res.generation_id);
      subscribe(res.generation_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "광고 생성에 실패했습니다.");
      setPhase("idle");
    }
  }

  // 후보 클릭 → 선택(DB) 후 모달 오픈 (게시·집행이 selected_candidate 검증을 통과하도록)
  async function openCandidate(candidate: GeneratorCandidate) {
    if (!detail) return;
    setSelectError(null);
    setModalCandidate(candidate);
    try {
      await api.generator.select(detail.generation_id, candidate.candidate_id);
    } catch (e) {
      setSelectError(e instanceof Error ? e.message : "후보 선택에 실패했습니다.");
    }
  }

  const activeStages =
    mode === "improve" ? IMPROVE_STAGES : format === "carousel" ? CAROUSEL_STAGES : STAGES;
  const currentIdx = activeStages.findIndex((s) => s.key === progress.stage);

  return (
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        {/* 헤더 */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-ink mb-2">광고 제너레이터</h1>
          <p className="text-sm text-ink-tertiary">
            상품 정보를 입력하면 AI가 전략이 다른 광고 후보 3종을 생성합니다 · 생성/개선 모드 지원
          </p>
        </div>

        <div className="grid grid-cols-5 gap-5">
          {/* ── 좌측 폼 ── */}
          <div className="col-span-2 space-y-4">
            {/* ── 프로젝트 선택 (생성 결과 저장 대상) ── */}
            <div className={`${cardCls} p-6`}>
              <label className={labelCls}>
                프로젝트 <span className="text-[#F74D4D]">*</span>
              </label>
              {projects.length === 0 ? (
                <p className="text-sm text-ink-tertiary">
                  선택할 프로젝트가 없습니다. 왼쪽 패널에서 프로젝트를 먼저 만들어 주세요.
                </p>
              ) : (
                <Select
                  aria-label="프로젝트 선택"
                  placeholder="프로젝트를 선택하세요"
                  value={selectedProject?.id ?? ""}
                  onChange={(v) => selectProject(v || null)}
                  options={projects.map((p) => ({ value: p.id, label: p.name }))}
                />
              )}
            </div>

            <div className={`${cardCls} p-1 flex`}>
              {(["create", "improve"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    setMode(m);
                    resetResult();
                  }}
                  className={`flex-1 py-2 text-sm font-medium rounded-xl transition-colors ${
                    mode === m
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "text-ink-tertiary hover:text-ink-secondary dark:hover:text-[#E5E8EB]"
                  }`}
                >
                  {m === "create" ? "생성 모드" : "개선 모드"}
                </button>
              ))}
            </div>

            {/* ── 시뮬레이션 선택 (개선모드 전용) ── */}
            {mode === "improve" && (
              <div className={`${cardCls} p-6`}>
                <label className={labelCls}>
                  시뮬레이션 <span className="text-[#F74D4D]">*</span>
                </label>
                {!selectedProject ? (
                  <p className="text-sm text-ink-tertiary">
                    프로젝트를 먼저 선택하세요.
                  </p>
                ) : improveSims.length === 0 ? (
                  <p className="text-sm text-ink-tertiary">
                    이 프로젝트에 시뮬레이션이 없습니다.
                  </p>
                ) : (
                  <Select
                    aria-label="시뮬레이션 선택"
                    placeholder="개선할 시뮬레이션을 선택하세요"
                    value={selectedSimId}
                    onChange={loadSimulation}
                    options={improveSims.map((s) => ({
                      value: s.id,
                      label: `${s.ad_title ?? "시뮬레이션"} · ${s.sample_size}명`,
                    }))}
                  />
                )}
              </div>
            )}

            <div className={`${cardCls} p-6 space-y-4`}>
              <div>
                <h2 className="text-sm font-semibold text-ink">
                  {mode === "create" ? "생성 설정" : "개선 설정"}
                </h2>
                <p className="text-xs text-ink-tertiary mt-0.5">
                  {mode === "create"
                    ? "* 필수 항목"
                    : "프로젝트·시뮬레이션을 선택하면 정보가 자동으로 채워집니다"}
                </p>
              </div>

              {mode === "create" ? (
                <>
                  <div>
                    <label className={labelCls}>형식</label>
                    <div className="flex gap-2">
                      {(
                        [
                          ["single", "단일 광고"],
                          ["carousel", "카드뉴스 (3장)"],
                        ] as const
                      ).map(([f, label]) => (
                        <button
                          key={f}
                          type="button"
                          onClick={() => setFormat(f)}
                          className={`flex-1 py-2 text-sm font-medium rounded-xl border transition-colors ${
                            format === f
                              ? "border-primary text-primary bg-primary-subtle"
                              : "border-line text-ink-tertiary hover:text-primary"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
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
                      상품 이미지{" "}
                      <span className="text-ink-tertiary font-normal">(선택 — 제공 시 상품 이미지 기반으로 광고 생성)</span>
                    </label>
                    <input
                      ref={productImageInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={handleProductImageChange}
                    />
                    {productImagePreviewUrl ? (
                      <div className="flex items-center gap-3 p-3 rounded-xl border border-line bg-[#F8F9FA] dark:bg-[#252D3D]">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={productImagePreviewUrl}
                          alt="상품 이미지 미리보기"
                          className="w-14 h-14 object-contain rounded-lg border border-line bg-card"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-ink-secondary mb-1.5">
                            이 이미지를 기반으로 광고 배경이 생성됩니다
                          </p>
                          <div className="flex gap-3">
                            <button
                              type="button"
                              disabled={productImageUploading}
                              onClick={() => productImageInputRef.current?.click()}
                              className="text-xs text-primary hover:underline disabled:opacity-50"
                            >
                              {productImageUploading ? "업로드 중..." : "교체"}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setProductImagePreviewUrl("");
                                setProductImageTempKey("");
                              }}
                              className="text-xs text-ink-tertiary hover:text-[#F74D4D] transition-colors"
                            >
                              제거
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <button
                        type="button"
                        disabled={productImageUploading}
                        onClick={() => productImageInputRef.current?.click()}
                        className={`${inputCls} text-left cursor-pointer`}
                      >
                        {productImageUploading
                          ? "업로드 중..."
                          : "PNG · JPG · WebP (최대 4MB)"}
                      </button>
                    )}
                    <p className="mt-1.5 text-xs text-ink-tertiary">
                      최대 4MB · PNG · JPG · WebP
                    </p>
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
                    <Select
                      aria-label="광고 목적"
                      value={objective}
                      onChange={setObjective}
                      options={OBJECTIVES.map((o) => ({
                        value: o.value,
                        label: o.label,
                      }))}
                    />
                  </div>
                </>
              ) : (
                <>
                  {improveLoading && (
                    <p className="text-sm text-ink-tertiary">
                      시뮬레이션 정보를 불러오는 중...
                    </p>
                  )}
                  {improveError && <p className="text-sm text-red-500">{improveError}</p>}
                  {improveData && (
                    <>
                      <div>
                        <label className={labelCls}>기존 광고 (개선 대상)</label>
                        {improveData.ad_asset_url && adRefImageSrc(improveData.ad_asset_url) ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={adRefImageSrc(improveData.ad_asset_url)!}
                            alt="기존 광고"
                            className="w-full rounded-xl border border-line"
                          />
                        ) : (
                          <div className="w-full rounded-xl border-2 border-dashed border-line bg-[#F8F9FA] dark:bg-[#252D3D] flex flex-col items-center justify-center gap-2 text-center p-8 min-h-[180px]">
                            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-ink-muted">
                              <rect x="3" y="3" width="18" height="18" rx="2" />
                              <circle cx="8.5" cy="8.5" r="1.5" />
                              <path d="M21 15l-5-5L5 21" />
                            </svg>
                            <p className="text-xs font-medium text-ink-tertiary">
                              등록된 광고 이미지가 없습니다
                            </p>
                            <p className="text-[11px] text-ink-muted">
                              시뮬레이션에서 광고 이미지를 업로드하면 여기에 표시됩니다
                            </p>
                          </div>
                        )}
                      </div>
                      <div>
                        <label className={labelCls}>제품명</label>
                        <input
                          className={`${inputCls} bg-surface-1`}
                          value={improveData.product_name}
                          readOnly
                        />
                      </div>
                      <div>
                        <label className={labelCls}>시뮬레이션 결과 요약</label>
                        <textarea
                          className={`${inputCls} min-h-16 bg-surface-1`}
                          value={improveData.summary}
                          readOnly
                        />
                      </div>
                      <div>
                        <label className={labelCls}>개선 방향 (시뮬레이션)</label>
                        {improveData.improvement_direction ? (
                          <textarea
                            className={`${inputCls} min-h-24 bg-surface-1`}
                            value={improveData.improvement_direction}
                            readOnly
                          />
                        ) : (
                          <p className="text-xs text-ink-tertiary">
                            이 시뮬레이션엔 개선 권고(토론)가 없어요. 수정 요청사항으로 개선 방향을 입력하세요.
                          </p>
                        )}
                      </div>
                      {improveData.plain_summary && (
                        <div>
                          <label className={labelCls}>AI 광고 분석</label>
                          <div className="rounded-xl border border-line bg-surface-1 p-3 text-xs text-ink-muted whitespace-pre-wrap leading-relaxed">
                            {improveData.plain_summary}
                          </div>
                        </div>
                      )}
                      {improveData.product_cutout_s3_key && (
                        <div>
                          <label className={labelCls}>제품 컷아웃 (개선 소재)</label>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={adRefImageSrc(improveData.product_cutout_s3_key)!}
                            alt="제품 누끼"
                            className="w-full max-h-48 object-contain rounded-xl border border-line bg-[#F0F0F0] dark:bg-[#1A1F2E]"
                          />
                        </div>
                      )}
                    </>
                  )}
                  <div>
                    <label className={labelCls}>수정 요청사항</label>
                    <textarea
                      className={`${inputCls} min-h-16 resize-y`}
                      value={fixRequests}
                      onChange={(e) => setFixRequests(e.target.value)}
                      placeholder={"예: 전체적으로 더 밝고 활기찬 분위기로 바꿔주세요\n제품을 더 크고 선명하게 부각해주세요\n색상을 브랜드 컬러에 맞게 통일해주세요\n\n비워두면 시뮬레이션 개선 방향만 반영됩니다"}
                    />
                  </div>
                </>
              )}

              {/* 공통 옵션 */}
              <button
                type="button"
                onClick={() => setShowOptional((v) => !v)}
                className="text-xs font-medium text-primary hover:underline"
              >
                {showOptional
                  ? "▲ 선택 항목 접기"
                  : "▼ 선택 항목 (브랜드 컬러·로고·톤앤매너·사이즈)"}
              </button>

              {showOptional && (
                <div className="space-y-4 pt-1">
                  {/* ── 브랜드 키트 (저장/불러오기) ── */}
                  <div className="space-y-2 pb-4 border-b border-line">
                    <label className={labelCls}>브랜드 키트</label>
                    <div className="flex gap-2">
                      <Select
                        aria-label="브랜드 키트 불러오기"
                        className="flex-1"
                        placeholder="저장된 키트 불러오기..."
                        value={selectedKitId}
                        onChange={applyKit}
                        options={kits.map((k) => ({
                          value: k.id,
                          label: k.name,
                        }))}
                      />
                      {selectedKitId && (
                        <button
                          type="button"
                          onClick={deleteKit}
                          className="px-3 py-2 text-sm text-red-500 border border-red-200 dark:border-red-900/40 rounded-xl hover:bg-red-50 dark:hover:bg-red-900/20 shrink-0"
                        >
                          삭제
                        </button>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <input
                        className={inputCls}
                        value={kitName}
                        onChange={(e) => setKitName(e.target.value)}
                        placeholder="현재 설정을 새 키트로 저장 (이름)"
                      />
                      <button
                        type="button"
                        onClick={saveKit}
                        disabled={!kitName.trim()}
                        className="px-3 py-2 text-sm font-medium text-white bg-primary rounded-xl hover:bg-primary-hover disabled:opacity-40 shrink-0"
                      >
                        저장
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className={labelCls}>
                      브랜드 컬러{" "}
                      <span className="font-normal text-ink-tertiary">
                        · 미적용 시 자동 배색
                      </span>
                    </label>
                    <div className="flex gap-2 items-center">
                      {/* 네이티브 컬러 입력은 빈 값을 못 담아 숨기고, 커스텀 스와치로 미적용을 표현한다. */}
                      <input
                        ref={colorInputRef}
                        type="color"
                        value={brandColor || "#2563EB"}
                        onChange={(e) => setBrandColor(e.target.value)}
                        className="sr-only"
                        tabIndex={-1}
                        aria-hidden="true"
                      />
                      <button
                        type="button"
                        onClick={() => colorInputRef.current?.click()}
                        title={brandColor || "미적용 — 클릭해 색상 지정"}
                        aria-label={
                          brandColor ? `브랜드 컬러 ${brandColor}` : "브랜드 컬러 미적용"
                        }
                        className="w-10 h-10 shrink-0 rounded-lg border border-line cursor-pointer bg-card"
                        style={
                          brandColor
                            ? { backgroundColor: brandColor }
                            : {
                                backgroundImage:
                                  "linear-gradient(to top right, transparent calc(50% - 1px), #F74D4D calc(50% - 1px), #F74D4D calc(50% + 1px), transparent calc(50% + 1px))",
                              }
                        }
                      />
                      <input
                        className={inputCls}
                        value={brandColor}
                        onChange={(e) => setBrandColor(e.target.value)}
                        placeholder="미적용 (예: #2563EB)"
                      />
                      {brandColor && (
                        <button
                          type="button"
                          onClick={() => setBrandColor("")}
                          className="shrink-0 text-xs text-ink-tertiary hover:text-[#F74D4D] transition-colors"
                        >
                          지우기
                        </button>
                      )}
                    </div>
                  </div>

                  <div>
                    <label className={labelCls}>
                      브랜드 로고{" "}
                      <span className="font-normal text-ink-tertiary">
                        · 한 변이 1024px 이하여야 합니다
                      </span>
                    </label>
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
                          className="w-14 h-14 object-contain rounded-lg border border-line bg-card"
                        />
                        <button
                          type="button"
                          disabled={logoUploading}
                          onClick={() => logoInputRef.current?.click()}
                          className="text-xs text-primary hover:underline disabled:opacity-50"
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
                              ? "border-primary bg-primary/10 text-primary font-semibold"
                              : "border-line text-ink-tertiary"
                          }`}
                        >
                          {s.label}
                        </button>
                      ))}
                    </div>
                  </div>

                </div>
              )}

              <button
                type="button"
                disabled={!canSubmit || phase === "generating"}
                onClick={startGeneration}
                className="w-full py-3 rounded-xl text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary-hover disabled:bg-[#E5E8EB] disabled:text-ink-muted dark:disabled:bg-[#252D3D] dark:disabled:text-ink-muted disabled:cursor-not-allowed transition-colors"
              >
                {phase === "generating"
                  ? "생성 중..."
                  : format === "carousel"
                    ? "카드뉴스 생성하기"
                    : mode === "improve"
                      ? "광고 생성하기"
                      : "광고 후보 3종 생성하기"}
              </button>
            </div>

            {/* 서버 워커 자동 점검 결과 — 결과 있을 때만 표시 */}
            <WorkerRunsCard runs={workerRuns} />
          </div>

          {/* ── 우측: 진행 / 결과 ── */}
          <div className="col-span-3">
            <div className={`${cardCls} p-6 min-h-[520px]`}>
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-sm font-semibold text-ink">생성 결과</h2>
                {phase === "done" && (
                  <button
                    type="button"
                    onClick={resetResult}
                    className="text-xs text-ink-tertiary hover:text-primary transition-colors"
                  >
                    새로 생성하기
                  </button>
                )}
              </div>
              <p className="text-xs text-ink-tertiary mb-5">
                {format === "carousel"
                  ? "관심끌기·가치전달·행동유도 3장 구성 · 카드를 클릭하면 게시·광고 집행을 할 수 있어요"
                  : mode === "improve"
                    ? "시뮬레이션 피드백 기반 개선 광고 · 카드를 클릭하면 게시·광고 집행을 할 수 있어요"
                    : "전략이 서로 다른 광고 3종 · 카드를 클릭하면 게시·광고 집행을 할 수 있어요"}
              </p>

              {error && (
                <ErrorCard
                  message={error}
                  onRetry={phase === "idle" ? startGeneration : undefined}
                  className="mb-4"
                />
              )}

              {/* 진행 중 (SSE) */}
              {phase === "generating" && (
                <div className="py-2">
                  <div className="mb-6">
                    <div className="flex justify-between items-baseline mb-2">
                      <span className="text-sm font-semibold text-ink">
                        {progress.message}
                      </span>
                      <span className="text-xs text-ink-tertiary">{progress.pct}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-surface-1 overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all duration-500"
                        style={{ width: `${progress.pct}%` }}
                      />
                    </div>
                  </div>
                  <ul className="space-y-3">
                    {activeStages.map((s, i) => {
                      const done = currentIdx > i || progress.pct >= 100;
                      const active = currentIdx === i;
                      return (
                        <li key={s.key} className="flex items-center gap-3 text-sm">
                          <span
                            className={`w-5 h-5 flex items-center justify-center rounded-full text-[10px] font-bold ${
                              done
                                ? "bg-[#00C471] text-white"
                                : active
                                  ? "bg-primary text-primary-foreground animate-pulse"
                                  : "bg-surface-1 text-ink-muted"
                            }`}
                          >
                            {done ? "✓" : i + 1}
                          </span>
                          <span
                            className={
                              done || active
                                ? "text-ink"
                                : "text-ink-muted"
                            }
                          >
                            {s.label}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  <p className="mt-6 text-xs text-ink-tertiary">
                    {mode === "improve"
                      ? "이미지 1장을 생성하는 데 1분 정도 걸릴 수 있어요."
                      : format === "carousel"
                        ? "카드뉴스 3장을 생성하는 데 1~2분 정도 걸릴 수 있어요."
                        : "이미지 3장을 생성하는 데 2~3분 정도 걸릴 수 있어요."}
                  </p>
                </div>
              )}

              {/* 결과 (후보 세로 정렬) */}
              {phase === "done" && detail && (
                <div className="flex flex-col gap-3">
                  <div className="flex justify-end gap-2">
                    {mode === "improve" && canSubmit && (
                      <button
                        type="button"
                        onClick={startGeneration}
                        className="flex items-center gap-1.5 text-xs text-ink-secondary border border-line rounded-lg px-3 py-1.5 hover:border-primary hover:text-primary transition-colors"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                          <path fillRule="evenodd" d="M13.836 2.477a.75.75 0 0 1 .75.75v3.182a.75.75 0 0 1-.75.75h-3.182a.75.75 0 0 1 0-1.5h1.37l-.84-.841a4.5 4.5 0 0 0-7.08.932.75.75 0 0 1-1.3-.75 6 6 0 0 1 9.44-1.242l.84.84V3.227a.75.75 0 0 1 .75-.75Zm-.911 7.5A.75.75 0 0 1 13.199 11a6 6 0 0 1-9.44 1.241l-.84-.84v1.371a.75.75 0 0 1-1.5 0V9.591a.75.75 0 0 1 .75-.75H5.35a.75.75 0 0 1 0 1.5H3.98l.841.841a4.5 4.5 0 0 0 7.08-.932.75.75 0 0 1 1.025-.273Z" clipRule="evenodd" />
                        </svg>
                        재생성
                      </button>
                    )}
                    {/* #2 — 생성 시안으로 시뮬레이션 돌리기(채팅의 시뮬 제안으로 이동, 첫 시안 프리필) */}
                    <button
                      type="button"
                      className="flex items-center gap-1.5 text-xs text-primary border border-primary/40 rounded-lg px-3 py-1.5 hover:bg-primary-subtle transition-colors"
                      onClick={() => {
                        // #3에서 만든 '제안 새 채팅'을 연다(기존 대화 아님).
                        const sid = localStorage.getItem(
                          `gen_sim_session_${detail.generation_id}`,
                        );
                        openChat(sid ?? null);
                      }}
                    >
                      🧪 시뮬레이션 돌리기
                    </button>
                    <button
                      type="button"
                      className="flex items-center gap-1.5 text-xs text-ink-secondary border border-line rounded-lg px-3 py-1.5 hover:border-primary hover:text-primary transition-colors"
                      onClick={async () => {
                        const res = await authedFetch(`${API_BASE}/api/generator/generations/${detail.generation_id}/download-zip`);
                        const blob = await res.blob();
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `ads-${detail.generation_id.slice(0, 8)}.zip`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
                        <path d="M8 1a.75.75 0 0 1 .75.75v6.69l1.97-1.97a.75.75 0 1 1 1.06 1.06l-3.25 3.25a.75.75 0 0 1-1.06 0L4.22 7.53a.75.75 0 0 1 1.06-1.06l1.97 1.97V1.75A.75.75 0 0 1 8 1ZM2.5 13.75a.75.75 0 0 1 .75-.75h9.5a.75.75 0 0 1 0 1.5h-9.5a.75.75 0 0 1-.75-.75Z" />
                      </svg>
                      전체 ZIP 다운로드
                    </button>
                  </div>
                  {detail.candidates.map((c) => (
                    <CandidateCard
                      key={c.candidate_id}
                      candidate={c}
                      onClick={() => openCandidate(c)}
                      isCarousel={(detail.input?.format as string | undefined) === "carousel"}
                    />
                  ))}
                </div>
              )}

              {/* 대기 */}
              {phase === "idle" && !error && (
                <div className="flex flex-col items-center justify-center py-20 border-2 border-dashed border-line rounded-xl gap-2">
                  <p className="text-xs text-ink-muted">
                    좌측에서 정보를 입력하고 생성을 시작하세요
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {modalCandidate && detail && (
          <CandidateModal
            generationId={detail.generation_id}
            candidate={modalCandidate}
            selectError={selectError}
            onClose={() => setModalCandidate(null)}
            isCarousel={(detail.input?.format as string | undefined) === "carousel"}
          />
        )}
      </div>
  );
}
