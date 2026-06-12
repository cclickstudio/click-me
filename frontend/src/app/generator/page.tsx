"use client";

import { useState } from "react";
import AppLayout from "@/components/AppLayout";
import { api } from "@/lib/api";
import type {
  GenerationDetail,
  GeneratorCandidate,
  PublishResult,
  SSEProgressEvent,
} from "@/lib/types";

type Step = "input" | "generating" | "candidates" | "selected";

const OBJECTIVES = [
  { value: "awareness", label: "브랜드 인지" },
  { value: "conversion", label: "구매 전환" },
  { value: "lead_gen", label: "리드 수집" },
  { value: "app_install", label: "앱 설치" },
  { value: "retention", label: "재구매 유도" },
  { value: "product_launch", label: "신제품 런칭" },
  { value: "promotion", label: "프로모션 반응" },
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

const inputCls =
  "w-full px-3 py-2.5 text-sm rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#252D3D] text-[#191F28] dark:text-[#F2F4F6] placeholder-[#B0B8C1] dark:placeholder-[#4B5563] focus:outline-none focus:border-[#3182F6] transition-colors";
const labelCls = "block text-xs font-medium text-[#4E5968] dark:text-[#9CA3AF] mb-1.5";
const cardCls =
  "bg-white dark:bg-[#1C2333] border border-[#E5E8EB] dark:border-[#2D3748] rounded-2xl transition-colors";

export default function GeneratorPage() {
  const [step, setStep] = useState<Step>("input");

  // 입력 폼
  const [productName, setProductName] = useState("");
  const [productDescription, setProductDescription] = useState("");
  const [targetAudience, setTargetAudience] = useState("");
  const [objective, setObjective] = useState("conversion");
  const [showOptional, setShowOptional] = useState(false);
  const [brandColor, setBrandColor] = useState("");
  const [brandLogoUrl, setBrandLogoUrl] = useState("");
  const [toneAndManner, setToneAndManner] = useState("");
  const [sizeIdx, setSizeIdx] = useState(0);

  // 진행/결과
  const [progress, setProgress] = useState({ stage: "", pct: 0, message: "" });
  const [detail, setDetail] = useState<GenerationDetail | null>(null);
  const [selected, setSelected] = useState<GeneratorCandidate | null>(null);
  const [error, setError] = useState("");

  // 게시
  const [caption, setCaption] = useState("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<PublishResult | null>(null);

  const canStart = productName.trim() && productDescription.trim() && targetAudience.trim();

  function reset() {
    setStep("input");
    setDetail(null);
    setSelected(null);
    setPublishResult(null);
    setCaption("");
    setError("");
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
        brand_logo_url: brandLogoUrl || null,
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

  const header = (
    <div className="mb-8">
      <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 제너레이터</h1>
      <p className="text-sm text-[#8B95A1] dark:text-[#6B7280] mt-1">
        상품 정보를 입력하면 AI가 전략이 다른 광고 후보 3종을 생성합니다
      </p>
    </div>
  );

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
            {/* 입력 폼 */}
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

                {/* 선택 항목 */}
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
                      <label className={labelCls}>브랜드 로고 URL</label>
                      <input
                        className={inputCls}
                        value={brandLogoUrl}
                        onChange={(e) => setBrandLogoUrl(e.target.value)}
                        placeholder="https://..."
                      />
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

            {/* 결과 placeholder */}
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
            {/* 미리보기 + 게시 */}
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
                        META_ACCESS_TOKEN / META_IG_USER_ID를 설정하면 실제 Instagram에
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
            </div>

            {/* QA + 생성 이유 */}
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

          {/* 게시 승인 모달 */}
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
